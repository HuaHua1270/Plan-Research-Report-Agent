"""Built-in tools shipped with the Agent framework."""

from importlib import import_module

__all__ = [
    "TaskTool",
    "TodoWriteTool",
    "TodoItem",
    "TodoList",
    "DevLogTool",
    "DevLogEntry",
    "DevLogStore",
]

_EXPORTS = {
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
