
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum
import json


class ToolStatus(Enum):
    """工具执行状态枚举"""
    SUCCESS = "success"  # 任务完全按预期执行
    PARTIAL = "partial"  # 结果可用但存在折扣（截断、回退、部分失败）
    ERROR = "error"      # 无有效结果（致命错误）

@dataclass
class ToolResponse:
   """工具响应数据类

    标准化的工具响应格式，包含：
    - status: 执行状态（success/partial/error）
    - text: 给 LLM 阅读的格式化文本
    - data: 结构化数据载荷
    - error_info: 错误信息（仅 status=error 时）
    - stats: 运行统计（时间、token等）
    - context: 上下文信息（参数、环境等）

   """

   status: ToolStatus
   text: str
   data: Dict[str, Any] = field(default_factory=dict)
   error_info: Optional[Dict[str, str]] = None
   stats: Optional[Dict[str, Any]] = None
   context: Optional[Dict[str, Any]] = None

   @classmethod
   def success(
           cls,
           text: str,
           data: Optional[Dict[str, Any]] = None,
           stats: Optional[Dict[str, Any]] = None,
           context: Optional[Dict[str, Any]] = None
   ) -> 'ToolResponse':
       """快速创建成功响应

       Args:
           text: 给 LLM 阅读的文本
           data: 结构化数据
           stats: 运行统计
           context: 上下文信息
       """
       return cls(
           status=ToolStatus.SUCCESS,
           text=text,
           data=data or {},
           stats=stats,
           context=context
       )

   @classmethod
   def partial(
           cls,
           text: str,
           data: Optional[Dict[str, Any]] = None,
           stats: Optional[Dict[str, Any]] = None,
           context: Optional[Dict[str, Any]] = None
   ) -> 'ToolResponse':
       """快速创建部分成功响应

       Args:
           text: 给 LLM 阅读的文本（应说明部分成功的原因）
           data: 结构化数据
           stats: 运行统计
           context: 上下文信息
       """
       return cls(
           status=ToolStatus.PARTIAL,
           text=text,
           data=data or {},
           stats=stats,
           context=context
       )

   @classmethod
   def error(
           cls,
           code: str,
           message: str,
           stats: Optional[Dict[str, Any]] = None,
           context: Optional[Dict[str, Any]] = None
   ) -> 'ToolResponse':
       """快速创建错误响应

       Args:
           code: 错误码（来自 ToolErrorCode）
           message: 错误消息
           stats: 运行统计
           context: 上下文信息
       """
       return cls(
           status=ToolStatus.ERROR,
           text=message,
           data={},
           error_info={"code": code, "message": message},
           stats=stats,
           context=context
       )
