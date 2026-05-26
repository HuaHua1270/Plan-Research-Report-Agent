from __future__ import annotations

import json
import os
from typing import Any, Dict, List
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ddgs import DDGS

from MyAgentFrame.tool.base import Tool, ToolParameter
from MyAgentFrame.tool.error import ToolErrorCode
from MyAgentFrame.tool.response import ToolResponse

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None


class SearchTool(Tool):
    """Web search tool for research agents.

    Use cases:
        - Find current public web information for a research subtopic.
        - Collect source URLs, titles, and short snippets for later summarization.
        - Compare results across multiple search providers with Advanced mode.

    Parameters:
        query:
            Required search query. The tool also accepts ``input`` as a fallback
            when it is called by a generic tool registry.
        engine:
            Optional search engine. Supported values:
            - ``DuckDuckGo``: no API key required, good default search source.
            - ``Tavily``: API-backed search, requires ``TAVILY_API_KEY``.
            - ``Advanced``: mixed search that combines DuckDuckGo and Tavily,
              deduplicates results, and returns partial results if one source fails.
        max_results:
            Optional result limit. Values are clamped to 1-10.

    Features:
        - Stateless and safe to register once in ToolRegistry.
        - Returns a standard ToolResponse with readable text and structured
          ``data.results`` entries.
        - Normalizes URLs for deduplication, including removal of ``utm_*``
          tracking parameters.
        - Reports partial success when Advanced mode has usable results from at
          least one source.

    Example:
        >>> tool = SearchTool()
        >>> response = tool.run({
        ...     "query": "AI agent research workflow",
        ...     "engine": "Advanced",
        ...     "max_results": 5,
        ... })
        >>> response.data["results"][0]["url"]
        'https://...'
    """

    default_engine: str = "DuckDuckGo"
    max_results: int = 5

    def __init__(self, default_engine: str = "DuckDuckGo", max_results: int = 5):
        super().__init__(
            name="Search",
            description=(
                "Web search tool. Provide query and optional engine. "
                "Supported engines: DuckDuckGo, Tavily, Advanced. "
                "Returns readable text and structured search results."
            ),
            default_engine=default_engine,
            max_results=max_results,
        )

    def get_parameters(self) -> List[ToolParameter]:
        """Return the function-calling schema parameters exposed to the LLM."""
        return [
            ToolParameter(
                name="query",
                type="string",
                description="Search query text.",
            ),
            ToolParameter(
                name="engine",
                type="string",
                description="Optional search engine: DuckDuckGo, Tavily, or Advanced. Default is DuckDuckGo.",
                required=False,
                default=self.default_engine,
            ),
            ToolParameter(
                name="max_results",
                type="integer",
                description="Maximum number of results to return. Default is 5; allowed range is 1-10.",
                required=False,
                default=self.max_results,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        """Execute a search request and return a standard ToolResponse."""
        query = self._get_query(parameters)
        if not query:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="SearchTool requires a non-empty query.",
                context={"parameters": parameters},
            )

        engine = str(parameters.get("engine") or self.default_engine)
        max_results = self._normalize_max_results(parameters.get("max_results"))

        try:
            if engine == "DuckDuckGo":
                return self._duckduckgo_search(query, max_results)
            if engine == "Tavily":
                return self._tavily_search(query, max_results)
            # # 50刀费用
            # if engine == "Perplexity":
            #     return self._perplexity_search(query, max_results)
            # # 外国服务器搭建
            # if engine == "SearXNG":
            #     return self._searxng_search(query, max_results)
            if engine == "Advanced":
                return self._advanced_search(query, max_results)

            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message=f"Unsupported search engine: {engine}",
                context={
                    "query": query,
                    "engine": engine,
                    "supported_engines": ["DuckDuckGo", "Tavily", "Advanced"],
                },
            )
        except Exception as exc:
            return ToolResponse.error(
                code=ToolErrorCode.API_ERROR,
                message=f"Search failed: {exc}",
                stats={"engine": engine},
                context={"query": query, "engine": engine},
            )

    def _get_query(self, parameters: Dict[str, Any]) -> str:
        query = parameters.get("query") or parameters.get("input") or ""
        return str(query).strip()

    def _normalize_max_results(self, value: Any) -> int:
        try:
            max_results = int(value or self.max_results)
        except (TypeError, ValueError):
            max_results = self.max_results
        return max(1, min(max_results, 10))

    def _duckduckgo_search(self, query: str, max_results: int) -> ToolResponse:
        with DDGS() as ddgs:
            raw_results = list(
                ddgs.text(
                    query,
                    region="wt-wt",
                    safesearch="moderate",
                    max_results=max_results,
                )
            )

        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("href") or item.get("url", ""),
                "snippet": item.get("body", ""),
                "source": "DuckDuckGo",
            }
            for item in raw_results
        ]
        return self._success_response(query, "DuckDuckGo", results)

    def _tavily_search(self, query: str, max_results: int) -> ToolResponse:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="TAVILY_API_KEY is not configured.",
                context={"query": query, "engine": "Tavily"},
            )
        if TavilyClient is None:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="tavily package is not installed.",
                context={"query": query, "engine": "Tavily"},
            )

        client = TavilyClient(api_key=api_key)
        response = client.search(query=query, max_results=max_results)
        raw_results = response.get("results", []) if isinstance(response, dict) else []

        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "source": "Tavily",
                "score": item.get("score"),
            }
            for item in raw_results
        ]
        return self._success_response(query, "Tavily", results)

    def _advanced_search(self, query: str, max_results: int) -> ToolResponse:
        """Run all available search providers and merge their results."""
        responses = {
            "DuckDuckGo": self._duckduckgo_search(query, max_results),
            "Tavily": self._tavily_search(query, max_results),
        }

        results: list[dict[str, Any]] = []
        errors: dict[str, str] = {}
        source_counts: dict[str, int] = {}

        for engine, response in responses.items():
            if response.status.value == "success":
                engine_results = response.data.get("results", [])
                source_counts[engine] = len(engine_results)
                results.extend(engine_results)
            else:
                errors[engine] = response.text

        merged_results = self._dedupe_results(results)
        if not merged_results:
            return ToolResponse.error(
                code=ToolErrorCode.API_ERROR,
                message="Advanced search failed: no search engine returned usable results.",
                stats={
                    "engine": "Advanced",
                    "sources": list(responses.keys()),
                    "source_counts": source_counts,
                },
                context={
                    "query": query,
                    "errors": errors,
                },
            )

        text = self._format_results_text(query, "Advanced", merged_results)
        data = {
            "query": query,
            "engine": "Advanced",
            "results": merged_results,
            "errors": errors,
        }
        stats = {
            "engine": "Advanced",
            "sources": list(responses.keys()),
            "source_counts": source_counts,
            "result_count": len(merged_results),
            "error_count": len(errors),
        }
        context = {
            "query": query,
            "engine": "Advanced",
            "errors": errors,
        }

        if errors:
            return ToolResponse.partial(
                text=f"{text}\n\nSome search sources failed: {json.dumps(errors, ensure_ascii=False)}",
                data=data,
                stats=stats,
                context=context,
            )

        return ToolResponse.success(text=text, data=data, stats=stats, context=context)

    def _dedupe_results(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []

        for item in results:
            key = self._result_key(item)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return deduped

    def _result_key(self, item: dict[str, Any]) -> str:
        url = str(item.get("url") or "").strip()
        if url:
            return self._normalize_url(url)
        return str(item.get("title") or "").strip().lower()

    def _normalize_url(self, url: str) -> str:
        try:
            parts = urlsplit(url)
            query_items = [
                (key, value)
                for key, value in parse_qsl(parts.query, keep_blank_values=True)
                if not key.lower().startswith("utm_")
            ]
            return urlunsplit(
                (
                    parts.scheme.lower(),
                    parts.netloc.lower(),
                    parts.path.rstrip("/"),
                    urlencode(query_items),
                    "",
                )
            )
        except Exception:
            return url.strip().lower()

    def _success_response(self, query: str, engine: str, results: list[dict[str, Any]]) -> ToolResponse:
        text = self._format_results_text(query, engine, results)
        return ToolResponse.success(
            text=text,
            data={
                "query": query,
                "engine": engine,
                "results": results,
            },
            stats={
                "engine": engine,
                "result_count": len(results),
            },
            context={
                "query": query,
                "engine": engine,
            },
        )

    def _format_results_text(self, query: str, engine: str, results: list[dict[str, Any]]) -> str:
        if not results:
            return f"No search results found for: {query}"

        lines = [f"Search results for '{query}' via {engine}:"]
        for index, item in enumerate(results, start=1):
            title = item.get("title") or "Untitled"
            url = item.get("url") or ""
            snippet = item.get("snippet") or ""
            lines.append(f"{index}. {title}\n   URL: {url}\n   Snippet: {snippet}")
        return "\n".join(lines)

    def to_json(self, parameters: Dict[str, Any]) -> str:
        response = self.run(parameters)
        return json.dumps(response.data, ensure_ascii=False)

