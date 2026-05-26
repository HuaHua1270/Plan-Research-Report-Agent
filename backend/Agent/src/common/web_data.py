from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ResearchTaskRequest(BaseModel):
    req_id: str = Field(..., min_length=2, max_length=100, description="请求id")
    topic: str = Field(..., min_length=2, max_length=500, description="研究主题")
    language: Literal["zh", "en"] = Field(default="zh", description="最终报告语言")
    depth: Literal["quick", "standard", "deep"] = Field(default="standard", description="研究深度")
    max_subtopics: int = Field(default=5, ge=3, le=8, description="最多生成多少个子主题")
    need_citations: bool = Field(default=True, description="是否需要引用来源")
    report_format: Literal["markdown", "json"] = Field(default="markdown", description="报告输出格式")
    user_id: Optional[str] = Field(default=None, description="用户ID")


class ChildTaskRequest(BaseModel):
    parent_task_id: str
    child_task_id: str
    callback_url: str
    input_data: dict[str, Any]


class ChildTaskCallback(BaseModel):
    parent_task_id: str
    child_task_id: str
    stage: Literal["PLANNER", "RESEARCH", "REPORTER"]
    status: Literal["DONE", "FAILED"]
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class ChildTaskResponse(BaseModel):
    task_id: str
    parent_task_id: str
    status: Literal["PENDING", "RUNNING", "DONE", "FAILED"]
    stage: Literal["PLANNER", "RESEARCH", "REPORTER"]



