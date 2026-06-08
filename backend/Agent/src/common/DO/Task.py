from typing import Any, Optional, Literal

from pydantic import BaseModel, Field

class ParentTask(BaseModel):
    task_id: str
    status: Literal["PENDING", "RUNNING", "SUCCESS", "FAILED"]
    current_stage: Literal["PENDING", "PLANNER", "RESEARCH", "REPORTER", "DONE"]

    topic: str
    language: str = "zh"
    depth: str = "standard"
    max_subtopics: int = 5
    need_citations: bool = True
    report_format: str = "markdown"
    user_id: Optional[str] = None

    planner_task_id: Optional[str] = None
    research_task_id: Optional[str] = None
    reporter_task_id: Optional[str] = None

    plan_json: Optional[dict[str, Any]] = None
    research_json: Optional[dict[str, Any]] = None
    report_text: Optional[str] = None

    error: Optional[str] = None

class PlannerChildTask(BaseModel):
    task_id: str
    parent_task_id: str
    status: Literal["PENDING", "RUNNING", "DONE", "FAILED"]
    stage: Literal["PLANNER"] = "PLANNER"
    input_data: dict[str, Any]
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class ReportChildTask(BaseModel):
    task_id: str
    parent_task_id: str
    status: Literal["PENDING", "RUNNING", "DONE", "FAILED"]
    stage: Literal["REPORTER"] = "REPORTER"
    input_data: dict[str, Any]
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None

class ResearchChildTask(BaseModel):
    task_id: str
    parent_task_id: str
    status: Literal["PENDING", "RUNNING", "DONE", "FAILED"]
    stage: Literal["RESEARCH"] = "RESEARCH"
    input_data: dict[str, Any]
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None

