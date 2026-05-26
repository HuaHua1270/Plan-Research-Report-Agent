"""Core runtime primitives for the Agent framework."""

from importlib import import_module

__all__ = [
    "Agent",
    "BaseChatLLM",
    "Config",
    "SessionStore",
    "HelloAgentsException",
    "LLMException",
    "AgentException",
    "ConfigException",
    "ToolException",
    "EventType",
    "AgentEvent",
    "ExecutionContext",
    "StreamEventType",
    "StreamEvent",
    "StreamBuffer",
    "ToolCall",
    "LLMToolResponse",
    "LLMResponse",
    "StreamStats",
    "BaseChatLLMAdapter",
    "OpenAIAdapter",
    "AnthropicAdapter",
    "GeminiAdapter",
    "create_adapter",
]

from MyAgentFrame.core.BaseLLM import BaseChatLLM
from MyAgentFrame.core.Exception import HelloAgentsException, LLMException, ConfigException, AgentException, \
    ToolException
from MyAgentFrame.core.LLMAdapter import BaseChatLLMAdapter, OpenAIAdapter, AnthropicAdapter, GeminiAdapter, \
    create_adapter
from MyAgentFrame.core.LLMDataFormate import ToolCall, LLMToolResponse, LLMResponse, StreamStats
from MyAgentFrame.core.Session_store import SessionStore
from MyAgentFrame.core.config import Config
from MyAgentFrame.core.lifecycle import EventType, AgentEvent, ExecutionContext
from MyAgentFrame.core.streaming import StreamEventType, StreamEvent, StreamBuffer

_EXPORTS = {
    "Agent": ("core.Agent", "Agent"),
    "BaseChatLLM": ("core.BaseLLM", "BaseChatLLM"),
    "Config": ("core.config", "Config"),
    "SessionStore": ("core.Session_store", "SessionStore"),
    "HelloAgentsException": ("core.Exception", "HelloAgentsException"),
    "LLMException": ("core.Exception", "LLMException"),
    "AgentException": ("core.Exception", "AgentException"),
    "ConfigException": ("core.Exception", "ConfigException"),
    "ToolException": ("core.Exception", "ToolException"),
    "EventType": ("core.lifecycle", "EventType"),
    "AgentEvent": ("core.lifecycle", "AgentEvent"),
    "ExecutionContext": ("core.lifecycle", "ExecutionContext"),
    "StreamEventType": ("core.streaming", "StreamEventType"),
    "StreamEvent": ("core.streaming", "StreamEvent"),
    "StreamBuffer": ("core.streaming", "StreamBuffer"),
    "ToolCall": ("core.LLMDataFormate", "ToolCall"),
    "LLMToolResponse": ("core.LLMDataFormate", "LLMToolResponse"),
    "LLMResponse": ("core.LLMDataFormate", "LLMResponse"),
    "StreamStats": ("core.LLMDataFormate", "StreamStats"),
    "BaseChatLLMAdapter": ("core.LLMAdapter", "BaseChatLLMAdapter"),
    "OpenAIAdapter": ("core.LLMAdapter", "OpenAIAdapter"),
    "AnthropicAdapter": ("core.LLMAdapter", "AnthropicAdapter"),
    "GeminiAdapter": ("core.LLMAdapter", "GeminiAdapter"),
    "create_adapter": ("core.LLMAdapter", "create_adapter"),
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value

