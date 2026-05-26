"""Agent implementations and factory helpers."""

from importlib import import_module

__all__ = [
    "SimpleAgent",
    "ReActAgent",
    "ReflectionAgent",
    "Memory",
    "PlanSolveAgent",
    "Planner",
    "Executor",
    "create_agent",
    "default_subagent_factory",
]

from MyAgentFrame.agent.factory import create_agent, default_subagent_factory
from MyAgentFrame.agent.plan_solve_agent import PlanSolveAgent, Planner, Executor
from MyAgentFrame.agent.react_agent import ReActAgent
from MyAgentFrame.agent.reflection_agent import ReflectionAgent, Memory
from MyAgentFrame.agent.simple_agent import SimpleAgent

_EXPORTS = {
    "SimpleAgent": ("MyAgentFrame.agent.simple_agent", "SimpleAgent"),
    "ReActAgent": ("MyAgentFrame.agent.react_agent", "ReActAgent"),
    "ReflectionAgent": ("MyAgentFrame.agent.reflection_agent", "ReflectionAgent"),
    "Memory": ("MyAgentFrame.agent.reflection_agent", "Memory"),
    "PlanSolveAgent": ("MyAgentFrame.agent.plan_solve_agent", "PlanSolveAgent"),
    "Planner": ("MyAgentFrame.agent.plan_solve_agent", "Planner"),
    "Executor": ("MyAgentFrame.agent.plan_solve_agent", "Executor"),
    "create_agent": ("MyAgentFrame.agent.factory", "create_agent"),
    "default_subagent_factory": ("MyAgentFrame.agent.factory", "default_subagent_factory"),
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
