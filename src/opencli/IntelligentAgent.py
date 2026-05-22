import asyncio
from typing import Optional, Generator
import traceback
from textwrap import dedent
from llama_index.core.agent.workflow import FunctionAgent
from opencli.OpenCLITool import OpenCLITool


class IntelligentCLIAgent:
    """
    智能 CLI Agent，基于 llama_index 的 FunctionAgent
    自动判断用户意图并调用相应的 OpenCLI 工具
    """

    def __init__(
        self,
        llm,
        opencli_tool: Optional[OpenCLITool] = None,
        verbose: bool = False,
    ):
        self.llm = llm
        self.verbose = verbose
        self.opencli_tool = opencli_tool or OpenCLITool(verbose=verbose)

        # 获取所有工具
        self.tools = self.opencli_tool.get_all_tools()

        if self.verbose:
            print(f"[Agent] 已加载 {len(self.tools)} 个工具:")
            for tool in self.tools:
                print(f"  - {tool.metadata.name}: {tool.metadata.description}")

        # 创建 FunctionAgent
        self.agent = FunctionAgent(
            name="OpenCLIAgent",
            description="能够操作各种网站和浏览器的智能助手",
            system_prompt=self._get_system_prompt(),
            tools=self.tools,
            llm=self.llm,
            can_use_self_service_panel=False,
            verbose=verbose,
        )

    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return dedent("""\
            你是一个智能助手，能够使用 OpenCLI 工具来操作各种网站。

            ## 可用工具
            你可以使用以下工具来获取信息或操作浏览器：
            - **opencli_help**: 获取网站命令帮助（当你不确定时使用）
            - **opencli_execute**: 执行任意完整命令
            - **opencli_list**: 列出所有可用的网站名称

            ## 网站选择规则：
            1.
            如果用户明确使用标准网站名：
            bilibili
            zhihu
            github

            直接：
            opencli_help(site)

            2.
            如果用户使用别名、简称、中文名称：
            B站
            知乎
            新浪财经
            微博
            小红书

            先：
            opencli_list()

            找到最匹配的网站名后：
            opencli_help(site)

            3.
            禁止猜测网站名称。
            如果无法确认，必须先 list。

            例子：

            "B站热门"
            → bilibili
            → help

            "新浪财经新闻"
            → list
            → sinafinance
            → help

            "微博热搜"
            → list
            → weibo
            → help

            4 找到子命令后，执行该命令：
            opencli_execute(...)

            ## 规则：
            不要拼 opencli
            不要拼 cmd
            不要加 -f json

            ## 禁止：
            - 不要重复调用帮助

            ## 输出格式
            - 返回数据后，用友好的方式向用户展示结果, 结果有链接的一定要包括链接
            - 如果工具返回错误，解释可能的原因并给出建议
            """)

    def chat(self, message: str) -> str:
        """
        与 Agent 对话，自动调用工具完成任务

        Args:
            message: 用户输入的消息

        Returns:
            Agent 的回复内容
        """
        try:
            # 关键修改：使用 asyncio.run() 来运行异步的 agent.run
            # 创建新的事件循环来执行
            response = asyncio.run(self.agent.run(user_msg=message))

            if self.verbose:
                print(f"[Agent] Response: {response}")

            # 提取响应文本
            if hasattr(response, "response"):
                return response.response
            elif isinstance(response, str):
                return response
            else:
                return str(response)

        except Exception as e:
            error_msg = f"处理请求时出错: {str(e)}"
            if self.verbose:
                print(traceback.format_exc())
            return error_msg

    async def achat(self, message: str) -> str:
        """
        与 Agent 对话，自动调用工具完成任务（异步版本）

        Args:
            message: 用户输入的消息

        Returns:
            Agent 的回复内容
        """
        try:
            response = await self.agent.run(user_msg=message)
            # print("=========")
            # print("RESPONSE=", repr(response))
            if hasattr(response, "response"):
                return response.response
            elif isinstance(response, str):
                return response
            else:
                return str(response)

        except Exception as e:
            error_msg = f"处理请求时出错: {str(e)}"
            if self.verbose:
                print(traceback.format_exc())

            return error_msg

    def stream(self, message: str) -> Generator[str, None, None]:
        """流式对话"""
        try:
            # 使用 asyncio.run 运行异步生成器
            async def async_stream():
                async for chunk in self.agent.stream(user_msg=message):
                    if hasattr(chunk, "response") and chunk.response:
                        yield chunk.response
                    elif isinstance(chunk, str):
                        yield chunk

            # 运行异步生成器并同步消费
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                gen = async_stream()
                while True:
                    try:
                        chunk = loop.run_until_complete(gen.__anext__())
                        yield chunk
                    except StopAsyncIteration:
                        break
            finally:
                loop.close()

        except Exception as e:
            yield f"处理请求时出错: {str(e)}"

    async def astream(
        self,
        message,
    ):
        try:
            handler = self.agent.run(
                user_msg=message,
            )

            async for event in handler.stream_events():
                # 工具开始
                if hasattr(event, "tool_name") and event.tool_name:
                    if hasattr(event, "tool_kwargs"):
                        kwargs = event.tool_kwargs
                    else:
                        kwargs = {}
                    if hasattr(event, "tool_output"):
                        stage = "output"
                    else:
                        stage = "input"
                    yield {
                        "type": "tool",
                        "message": f"{event.tool_name}",
                        "stage": stage,
                        "kwargs": kwargs,
                    }
                    # print(event)
                # token
                if hasattr(event, "delta") and event.delta:
                    yield {
                        "type": "token",
                        "text": event.delta,
                    }

            await handler

        except Exception as e:
            yield {
                "type": "token",
                "text": str(e),
            }
            print(traceback.format_exc())
