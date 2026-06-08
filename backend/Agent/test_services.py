from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TOPIC = "大语言模型在软件开发中的应用"


@dataclass(frozen=True)
class ServiceEndpoint:
    name: str
    port: int
    path: str = "/health"


HEALTH_ENDPOINTS = [
    ServiceEndpoint("task-manager", 8000),
]


class ServiceTestError(RuntimeError):
    pass


class ServiceHttpError(ServiceTestError):
    def __init__(self, method: str, url: str, status_code: int, body: str):
        self.method = method
        self.url = url
        self.status_code = status_code
        self.body = body
        super().__init__(f"{method} {url} failed with HTTP {status_code}: {body}")


def service_url(base_url: str, port: int, path: str) -> str:
    parsed = urlsplit(base_url)
    hostname = parsed.hostname or "127.0.0.1"
    netloc = hostname
    if parsed.username:
        auth = parsed.username
        if parsed.password:
            auth = f"{auth}:{parsed.password}"
        netloc = f"{auth}@{netloc}"
    netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme or "http", netloc, path, "", ""))


def request_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None, timeout: float = 10.0) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(url=url, data=data, headers=headers, method=method)

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            if not body:
                return None
            return json.loads(body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ServiceHttpError(method, url, exc.code, body) from exc
    except URLError as exc:
        raise ServiceTestError(f"{method} {url} failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ServiceTestError(f"{method} {url} timed out") from exc
    except json.JSONDecodeError as exc:
        raise ServiceTestError(f"{method} {url} returned invalid JSON: {exc}") from exc


def check_health(base_url: str) -> bool:
    print("Checking service health...")
    ok = True

    for endpoint in HEALTH_ENDPOINTS:
        url = service_url(base_url, endpoint.port, endpoint.path)
        try:
            response = request_json(url, timeout=5)
            status = response.get("status") if isinstance(response, dict) else None
            service = response.get("service") if isinstance(response, dict) else None
            if status == "ok":
                print(f"  [OK] {endpoint.name} ({url}) service={service}")
            else:
                ok = False
                print(f"  [FAIL] {endpoint.name} ({url}) unexpected response: {response}")
        except ServiceTestError as exc:
            ok = False
            print(f"  [FAIL] {endpoint.name} ({url}) {exc}")

    return ok


def build_task_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "req_id": f"smoke-{uuid.uuid4().hex[:12]}",
        "topic": args.topic,
        "language": args.language,
        "depth": args.depth,
        "max_subtopics": args.max_subtopics,
        "need_citations": args.need_citations,
        "report_format": args.report_format,
    }


def print_task_summary(task: dict[str, Any]) -> None:
    status = task.get("status")
    stage = task.get("current_stage")
    error = task.get("error")
    print(f"  status={status} stage={stage}")
    if error:
        print(f"  error={error}")


def print_task_lost_hint(task_id: str, task_url: str, create_response: Any) -> None:
    print("[FAIL] Task was not found while polling.")
    print(f"  task_id={task_id}")
    print(f"  url={task_url}")
    print(f"  create_response={json.dumps(create_response, ensure_ascii=False)}")
    print("  hint=Task state is stored in PostgreSQL. Check DATABASE_URL, migrations,")
    print("       and whether task-manager is reading the same database used at creation time.")


def run_end_to_end(args: argparse.Namespace) -> bool:
    create_url = f"{args.base_url.rstrip('/')}/research-tasks"
    payload = build_task_payload(args)

    print(f"Creating research task: {create_url}")
    print(f"  req_id={payload['req_id']}")
    print(f"  topic={payload['topic']}")

    try:
        create_response = request_json(create_url, method="POST", payload=payload, timeout=30)
    except ServiceTestError as exc:
        print(f"[FAIL] Create task failed: {exc}")
        return False

    print(f"Create response: {json.dumps(create_response, ensure_ascii=False)}")

    if not isinstance(create_response, dict) or not create_response.get("task_id"):
        print("[FAIL] Create task response did not include task_id")
        return False

    task_id = create_response["task_id"]
    task_url = f"{args.base_url.rstrip('/')}/research-tasks/{task_id}"
    deadline = time.monotonic() + args.timeout_seconds
    last_stage = None
    last_status = None

    print(f"Polling task: {task_url}")
    while time.monotonic() < deadline:
        try:
            task = request_json(task_url, timeout=120)
        except ServiceHttpError as exc:
            if exc.status_code == 404:
                print_task_lost_hint(task_id, task_url, create_response)
                print(f"  response_body={exc.body}")
                return False
            print(f"[FAIL] Poll task failed: {exc}")
            return False
        except ServiceTestError as exc:
            print(f"[FAIL] Poll task failed: {exc}")
            return False

        if task is None:
            print_task_lost_hint(task_id, task_url, create_response)
            print("  response_body=null")
            return False

        if not isinstance(task, dict):
            print("[FAIL] Unexpected task response while polling.")
            print(f"  task_id={task_id}")
            print(f"  url={task_url}")
            print(f"  response_type={type(task).__name__}")
            print(f"  response_value={task!r}")
            return False

        status = task.get("status")
        stage = task.get("current_stage")

        if status != last_status or stage != last_stage:
            print_task_summary(task)
            last_status = status
            last_stage = stage

        if status == "SUCCESS":
            print("[OK] Task completed successfully.")
            report_text = task.get("report_text")
            if report_text:
                print("\nFinal report:")
                print(report_text)
            return True

        if status == "FAILED":
            print("[FAIL] Task failed.")
            if task.get("error"):
                print(f"Error: {task['error']}")
            return False

        time.sleep(args.poll_interval)

    print(f"[FAIL] Timed out after {args.timeout_seconds} seconds waiting for task {task_id}")
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke test the Agent backend services after start_services.py is running."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Task manager base URL. Default: {DEFAULT_BASE_URL}")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="Research topic to submit.")
    parser.add_argument("--language", choices=["zh", "en"], default="zh", help="Final report language.")
    parser.add_argument("--depth", choices=["quick", "standard", "deep"], default="quick", help="Research depth.")
    parser.add_argument("--max-subtopics", type=int, default=3, help="Maximum generated subtopics.")
    parser.add_argument(
        "--need-citations",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Request citations in the final report.",
    )
    parser.add_argument("--report-format", choices=["markdown", "json"], default="markdown", help="Report format.")
    parser.add_argument("--timeout-seconds", type=float, default=600.0, help="Maximum time to wait for completion.")
    parser.add_argument("--poll-interval", type=float, default=3.0, help="Seconds between status polls.")
    parser.add_argument("--health-only", action="store_true", help="Only check service health endpoints.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    health_ok = check_health(args.base_url)
    if not health_ok:
        print("[FAIL] One or more services are not healthy.")
        return 1

    if args.health_only:
        print("[OK] All services are healthy.")
        return 0

    return 0 if run_end_to_end(args) else 1


if __name__ == "__main__":
    sys.exit(main())
