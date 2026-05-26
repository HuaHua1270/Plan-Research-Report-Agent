"""Tool protocol, registry, responses, filters, and built-in tools."""

from importlib import import_module

__all__ = [
    "Tool",
    "ToolParameter",
    "tool_action",
    "ToolRegistry",
    "ToolResponse",
    "ToolStatus",
    "ToolErrorCode",
    "CircuitBreaker",
    "ToolFilter",
    "ReadOnlyFilter",
    "FullAccessFilter",
    "CustomFilter",
    "TaskTool",
    "TodoWriteTool",
    "TodoItem",
    "TodoList",
    "DevLogTool",
    "DevLogEntry",
    "DevLogStore",
]

from MyAgentFrame.tool.base import Tool, ToolParameter, tool_action
from MyAgentFrame.tool.breaker import CircuitBreaker
from MyAgentFrame.tool.builtin.devlog_tool import DevLogTool, DevLogEntry, DevLogStore
from MyAgentFrame.tool.builtin.task_tool import TaskTool
from MyAgentFrame.tool.builtin.todowrite_tool import TodoWriteTool, TodoItem, TodoList
from MyAgentFrame.tool.error import ToolErrorCode
from MyAgentFrame.tool.registry import ToolRegistry
from MyAgentFrame.tool.response import ToolResponse, ToolStatus
from MyAgentFrame.tool.tool_filter import ToolFilter, FullAccessFilter, ReadOnlyFilter, CustomFilter

_EXPORTS = {
    "Tool": ("MyAgentFrame.tool.base", "Tool"),
    "ToolParameter": ("MyAgentFrame.tool.base", "ToolParameter"),
    "tool_action": ("MyAgentFrame.tool.base", "tool_action"),
    "ToolRegistry": ("MyAgentFrame.tool.registry", "ToolRegistry"),
    "ToolResponse": ("MyAgentFrame.tool.response", "ToolResponse"),
    "ToolStatus": ("MyAgentFrame.tool.response", "ToolStatus"),
    "ToolErrorCode": ("MyAgentFrame.tool.error", "ToolErrorCode"),
    "CircuitBreaker": ("MyAgentFrame.tool.breaker", "CircuitBreaker"),
    "ToolFilter": ("MyAgentFrame.tool.tool_filter", "ToolFilter"),
    "ReadOnlyFilter": ("MyAgentFrame.tool.tool_filter", "ReadOnlyFilter"),
    "FullAccessFilter": ("MyAgentFrame.tool.tool_filter", "FullAccessFilter"),
    "CustomFilter": ("MyAgentFrame.tool.tool_filter", "CustomFilter"),
    "TaskTool": ("MyAgentFrame.tool.builtin.task_tool", "TaskTool"),
    "TodoWriteTool": ("MyAgentFrame.tool.builtin.todowrite_tool", "TodoWriteTool"),
    "TodoItem": ("MyAgentFrame.tool.builtin.todowrite_tool", "TodoItem"),
    "TodoList": ("MyAgentFrame.tool.builtin.todowrite_tool", "TodoList"),
    "DevLogTool": ("MyAgentFrame.tool.builtin.devlog_tool", "DevLogTool"),
    "DevLogEntry": ("MyAgentFrame.tool.builtin.devlog_tool", "DevLogEntry"),
    "DevLogStore": ("MyAgentFrame.tool.builtin.devlog_tool", "DevLogStore"),
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
