"""Conversation context, messages, and token accounting."""

from importlib import import_module

__all__ = [
    "BaseMessage",
    "HistoryManager",
    "TokenCounter",
]

from MyAgentFrame.context.history import HistoryManager
from MyAgentFrame.context.message import BaseMessage
from MyAgentFrame.context.token_counter import TokenCounter

_EXPORTS = {
    "BaseMessage": ("context.message", "BaseMessage"),
    "HistoryManager": ("context.history", "HistoryManager"),
    "TokenCounter": ("context.token_counter", "TokenCounter"),
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
