from typing import Optional, Callable, Dict, Any

from pydantic import Field

from MyAgentFrame.agent import ReflectionAgent


class ReportAgent(ReflectionAgent):
    """报告生成agent (基于ReflectionAgent的增强agent) """

    tool_call_listener: Optional[Callable] = Field(default=None)

    def _execute_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """执行工具调用并返回字符串结果"""
        # 解析参数
        # parsed_parameters = self._parse_parameters(arguments)

        # 调用工具
        result = super()._execute_tool_call(tool_name, arguments)

        # 通知监听器
        if self.tool_call_listener:
            self.tool_call_listener({
                "agent_name": self.name,
                "tool_name": tool_name,
                "parsed_parameters": arguments,
                "result": result,
            })
        return result