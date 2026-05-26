from enum import unique, Enum


@unique
class Status(Enum):
    """状态枚举"""

    """主流程阶段枚举"""
    PLANNER = "PLANNER"
    RESEARCH = "RESEARCH"
    REPORTER = "REPORTER"

    """任务状态"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    DONE = "DONE"
    FAILED = "FAILED"