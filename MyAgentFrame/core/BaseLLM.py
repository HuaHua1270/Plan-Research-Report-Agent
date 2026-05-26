
from pydantic import Field, BaseModel, model_validator, ConfigDict
import asyncio
from typing import Optional, Iterator, List, Dict, Union, Any, AsyncIterator

from .LLMAdapter import BaseChatLLMAdapter, create_adapter
from .LLMDataFormate import StreamStats, LLMResponse, LLMToolResponse


class BaseChatLLM(BaseModel):

     model_config = ConfigDict(populate_by_name=True ,extra = 'ignore')
     """多余参数的处理"""

     model: str = Field(default="gpt-3.5-turbo", alias="model")
     """使用的模型名称"""
     openai_api_key: str = Field(default= None , alias="api_key")
     """API Key"""
     openai_api_base: str = Field(default= None , alias="api_base")
     """API请求基础路径"""
     max_tokens: int | None = Field(default=512)
     """模型生成的最大token"""
     temperature: float | None = Field(default=1.0)
     """温度值，越低越精确"""
     request_timeout: float | tuple[float, float] | Any | None = Field(default=60.0, alias="timeout")
     """请求超时时间"""
     reasoning_effort: str | None = None
     """推理强度，支持`'minimal'`, `'low'`, `'medium'`,`'high'`"""

     _adapter : BaseChatLLMAdapter | None = None
     """聊天模型适配器"""
     last_call_stats: Optional[StreamStats] = None
     """流式调用最后一次的统计信息"""

     @model_validator(mode='before')
     @classmethod
     def preprocess_values(cls, values):
          """验证前预处理"""
          # 处理别名映射
          if isinstance(values, dict):
               # 字符串清理 去除首尾空格
               if isinstance(values.get('model_name'), str):
                    values['model_name'] = values['model_name'].strip()
               if isinstance(values.get('openai_api_key'), str):
                    values['openai_api_key'] = values['openai_api_key'].strip()

          #对于o1和gpt-5模型的特殊温度处理
          model = values.get("model_name") or values.get("model") or ""
          model_lower = model.lower()

          # 对于o1模型，将温度设置为1
          if model_lower.startswith("o1"):
               values["temperature"] = 1

          # For gpt-5 models, handle temperature restrictions. Temperature is supported
          # by gpt-5-chat and gpt-5 models with reasoning_effort='none' or
          if (
                  model_lower.startswith("gpt-5")
                  and ("chat" not in model_lower)
                  and values.get("reasoning_effort") != "none"
          ):
               temperature = values.get("temperature")
               if temperature is not None and temperature != 1:
                    # For gpt-5 (non-chat), only temperature=1 is supported
                    # So we remove any non-defaults
                    values.pop("temperature", None)
          return values

     @model_validator(mode='after')
     def validate_complete(self):
          """验证后处理"""
          # 检查 API Key 是否提供（从参数或环境变量）
          if not self.openai_api_key:
               raise ValueError("必须提供 openai_api_key 或设置 OPENAI_API_KEY 环境变量")

          # 检查 temperature 和 max_tokens 的组合逻辑
          if self.temperature is (0 <= self.temperature <= 2):
               raise ValueError("请设置合适的temperature值")

          self._adapter: BaseChatLLMAdapter = create_adapter(
               api_key=self.openai_api_key,
               base_url=self.openai_api_base,
               timeout=self.request_timeout,
               model=self.model
          )

          return self


     def invoke(self, messages: List[Dict], **kwargs) -> LLMResponse:
          # 合并参数
          call_kwargs = {
               "temperature": kwargs.pop("temperature", self.temperature),
          }
          if self.max_tokens:
               call_kwargs["max_tokens"] = kwargs.pop("max_tokens", self.max_tokens)
          call_kwargs.update(kwargs)

          return self._adapter.invoke(messages, **call_kwargs)


     def stream_invoke(self, messages: List[Dict], **kwargs) -> Iterator[str]:
          """流式调用，返回生成器"""

          call_kwargs = {
               "temperature": kwargs.pop("temperature", self.temperature),
          }
          if self.max_tokens:
               call_kwargs["max_tokens"] = kwargs.pop("max_tokens", self.max_tokens)
          call_kwargs.update(kwargs)


          for chunk in self._adapter.stream_invoke(messages, **call_kwargs):
               yield chunk
          # 保存统计信息
          if hasattr(self._adapter, 'last_stats'):
               self.last_call_stats = self._adapter.last_stats

     def invoke_with_tools(
             self,
             messages: List[Dict],
             tools: List[Dict],
             tool_choice: Union[str, Dict] = "auto",
             **kwargs
     ) -> LLMToolResponse:
          """工具调用（Function Calling）"""
          call_kwargs = {
               "temperature": kwargs.pop("temperature", self.temperature),
               "tool_choice": tool_choice
          }
          if self.max_tokens:
               call_kwargs["max_tokens"] = kwargs.pop("max_tokens", self.max_tokens)
          call_kwargs.update(kwargs)

          return self._adapter.invoke_with_tools(messages, tools , **call_kwargs)

     # ==================== 异步方法 ====================

     async def ainvoke(self, messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
          """
          异步非流式调用 LLM

          在线程池中运行同步 invoke 方法，避免阻塞事件循环

          Args:
              messages: 消息列表
              **kwargs: 其他参数（temperature, max_tokens等）

          Returns:
              LLMResponse: 包含内容、统计信息的响应对象

          Example:
              response = await llm.ainvoke([{"role": "user", "content": "你好"}])
              print(response.content)
          """
          loop = asyncio.get_event_loop()
          return await loop.run_in_executor(
               None,
               lambda: self.invoke(messages, **kwargs)
          )

     async def astream_invoke(
             self,
             messages: List[Dict[str, str]],
             **kwargs
     ) -> AsyncIterator[str]:
          """
          真正的异步流式调用 LLM（使用 adapter 的异步实现）

          Args:
              messages: 消息列表
              **kwargs: 其他参数

          Yields:
              str: 流式响应的文本片段（实时返回）

          Example:
              async for chunk in llm.astream_invoke(messages):
                  print(chunk, end="", flush=True)
          """
          # 使用 adapter 的异步流式方法
          async for chunk in self._adapter.astream_invoke(messages, **kwargs):
               yield chunk

          # 保存统计信息
          if hasattr(self._adapter, 'last_stats'):
               self.last_call_stats = self._adapter.last_stats

     async def ainvoke_with_tools(
             self,
             messages: List[Dict],
             tools: List[Dict],
             tool_choice: Union[str, Dict] = "auto",
             **kwargs
     ) -> LLMToolResponse:
          """
          异步调用 LLM 并支持工具调用（Function Calling）

          Args:
              messages: 消息列表
              tools: 工具 schema 列表
              tool_choice: 工具选择策略
              **kwargs: 其他参数

          Returns:
              统一的工具调用响应对象 (LLMToolResponse)
          """
          loop = asyncio.get_event_loop()
          return await loop.run_in_executor(
               None,
               lambda: self.invoke_with_tools(messages, tools, tool_choice, **kwargs)
          )






