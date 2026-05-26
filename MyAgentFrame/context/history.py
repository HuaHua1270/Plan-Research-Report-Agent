from typing import List

from typing import List, Optional, Dict, Any
from datetime import datetime

from pydantic import BaseModel

from ..context.message import BaseMessage


class HistoryManager(BaseModel):
    """历史管理与压缩"""

    # 不修改
    # 添加会话 ，总结会话 ， 获取会话 ， 删除会话
    min_retain_rounds : int = 10

    compression_threshold : float = 0.8

    _history: List[BaseMessage] = []

    def append(self , message : BaseMessage) -> None:
        """追加消息（只追加，不编辑）

        Args:
            message: 要追加的消息
        """
        self._history.append(message)

    def get_history(self) -> List[BaseMessage]:
        """获取历史副本

        Returns:
            历史消息列表的副本
        """
        return self._history.copy()

    def clear(self) -> None:
        """清空历史"""
        self._history.clear()

    def estimate_rounds(self) -> int:
        """预估完整轮次数

        一轮定义：1 user 消息 + N 条 assistant/tool/summary 消息

        Returns:
            完整轮次数
        """
        rounds = 0
        i = 0
        while i < len(self._history):
            if self._history[i].role == "user":
                rounds += 1
                # 跳过这一轮的后续消息
                i += 1
                while i < len(self._history) and self._history[i].role != "user":
                    i += 1
            else:
                i += 1
        return rounds

    def find_round_boundaries(self) -> List[int]:
        """查找每轮的起始索引

        Returns:
            每轮起始索引列表，例如 [0, 3, 7, 10]
        """
        boundaries = []
        for i, msg in enumerate(self._history):
            if msg.role == "user":
                boundaries.append(i)
        return boundaries

    def compress(self, summary: str) -> None:
        """压缩历史

        将旧历史替换为 summary 消息，保留最近 N 轮完整对话

        Args:
            summary: 历史摘要文本
        """
        # 检查是否有足够的轮次需要压缩
        rounds = self.estimate_rounds()
        if rounds <= self.min_retain_rounds:
            return

        # 找到所有轮次边界
        boundaries = self.find_round_boundaries()

        # 计算要保留的起始位置（保留最近 min_retain_rounds 轮）
        if len(boundaries) > self.min_retain_rounds:
            keep_from_index = boundaries[-self.min_retain_rounds]
        else:
            # 不足最小轮次，不压缩
            return

        # 生成 summary 消息
        summary_msg = BaseMessage(
            content=f"## Archived Session Summary\n{summary}",
            role="summary",
            metadata={"compressed_at": datetime.now().isoformat()}
        )

        # 替换历史：summary + 保留的最近轮次
        self._history = [summary_msg] + self._history[keep_from_index:]

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（用于会话保存）

        Returns:
            包含历史和元数据的字典
        """
        return {
            "history": [msg.to_dict() for msg in self._history],
            "created_at": datetime.now().isoformat(),
            "rounds": self.estimate_rounds()
        }

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """从字典加载（用于会话恢复）

        Args:
            data: 序列化的历史数据
        """
        self._history = [
            BaseMessage.from_dict(msg_data)
            for msg_data in data.get("history", [])
        ]

