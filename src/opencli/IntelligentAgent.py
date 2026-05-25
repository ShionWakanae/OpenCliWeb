import asyncio
import json
import traceback
from typing import Optional
from textwrap import dedent
from openai import AsyncOpenAI
from opencli.OpenCLITool import OpenCLITool


class IntelligentCLIAgent:
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        opencli_tool: Optional[OpenCLITool] = None,
        verbose=False,
    ):

        self.client = client
        self.model = model
        self.verbose = verbose
        self.opencli_tool = opencli_tool or OpenCLITool(verbose=verbose)
        self.tools = self.opencli_tool.get_tools()
        if verbose:
            print(f"[Agent] loaded {len(self.tools)} tools")
            for t in self.tools:
                print("-", t["function"]["name"])

    # prompt
    def _get_system_prompt(
        self,
    ):
        """获取系统提示词"""
        return dedent("""\
            你是一个智能助手，能够使用 OpenCLI 工具来操作各种网站。

            ## 可用工具
            你可以使用以下工具来获取信息或操作浏览器：
            - **get_today_date**: 获取当天日期
            - **opencli_help**: 获取网站命令帮助（当你不确定时使用）
            - **opencli_execute**: 执行任意完整命令
            - **opencli_list**: 列出所有可用的网站名称

            ## 日期规则：
            1. 
            如果用户输入了明确的日期，则不必调用 get_today_date 工具。

            2，
            如果用户提到类似'今天'，'明天'等不确定的日期，
            则调用 get_today_date 工具。
            并计算出用户真实希望的日期字符串。
            供后续命令使用。

            3，
            如果用户输入信息中没有日期内容，
            但发现在后续命令中需要日期，
            则调用 get_today_date 工具，
            并使用当天日期。

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
            不要加 -f 某格式

            ## 禁止：
            - 不要重复调用帮助
            - 同样的命令超过3次返回同样错误，停止工具调用，禁止继续重复。

            ## 输出格式
            - 返回数据后，用友好的方式向用户展示结果（Markdown格式，避免表格）
            - 不要隐藏结果项目，结果有链接的必须包括链接
            - 如果工具返回错误，解释可能的原因并给出建议
            """)

    # internal
    async def _run(
        self,
        message,
    ):
        messages = [
            {
                "role": "system",
                "content": self._get_system_prompt(),
            },
            {
                "role": "user",
                "content": message,
            },
        ]

        MAX_TOOL = 15
        for _ in range(MAX_TOOL):
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
                temperature=0.1,
                stream=True,
                stream_options={
                    "include_usage": True,
                },
                extra_body={
                    "chat_template_kwargs": {
                        "enable_thinking": False,
                    },
                    "enable_thinking": False,
                    "thinking": {
                        "type": "disabled",
                    },
                },
                max_tokens=8192,
            )

            content = ""
            tool_calls = {}
            async for chunk in stream:
                # usage chunk
                if chunk.usage:
                    yield {
                        "type": "usage",
                        "usage": chunk.usage.model_dump(),
                        "model": chunk.model,
                    }
                    continue

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # 普通文本
                if delta.content:
                    content += delta.content
                    yield {
                        "type": "token",
                        "text": delta.content,
                    }

                # tool call
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index

                        if idx not in tool_calls:
                            tool_calls[idx] = {
                                "id": "",
                                "name": "",
                                "args": "",
                            }
                        if tc.id:
                            tool_calls[idx]["id"] += tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls[idx]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls[idx]["args"] += tc.function.arguments

            # finish
            if not tool_calls:
                yield {
                    "type": "done",
                    "text": content,
                }
                return

            # assistant（只追加一次）
            messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["args"],
                            },
                        }
                        for tc in tool_calls.values()
                    ],
                }
            )

            # tool
            for tc in tool_calls.values():
                name = tc["name"]
                try:
                    args = json.loads(tc["args"] or "{}")
                except Exception as e:
                    print(f"Error parsing args: {e}")
                    if self.verbose:
                        print(traceback.format_exc())
                    args = {}

                yield {
                    "type": "tool",
                    "stage": "→",
                    "tool_name": name,
                    "message": name,
                    "kwargs": args,
                    "text_content": "",
                }

                try:
                    result = await asyncio.to_thread(
                        self.opencli_tool.execute, name, args
                    )

                except Exception as e:
                    result = {
                        "success": False,
                        "error": str(e),
                    }

                text = json.dumps(
                    result,
                    ensure_ascii=False,
                )

                yield {
                    "type": "tool",
                    "stage": "←",
                    "tool_name": name,
                    "message": name,
                    "kwargs": args,
                    "text_content": text,
                }

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": text,
                    }
                )

        print("tool loop overflow !!!")

    # public
    def chat(self, message):
        return asyncio.run(self.achat(message))

    async def achat(self, message):
        try:
            answer = ""
            async for event in self._run(message):
                if event["type"] == "token":
                    answer += event["text"]
            return answer

        except Exception as e:
            print(f"Error async for event in self._run: {e}")
            if self.verbose:
                print(traceback.format_exc())
            raise

    def stream(self, message):
        async def collect():
            async for event in self.astream(message):
                if event["type"] == "token":
                    yield (event["text"])

        loop = asyncio.new_event_loop()
        try:
            gen = collect()
            while True:
                try:
                    yield (loop.run_until_complete(gen.__anext__()))
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    async def astream(self, message):
        try:
            async for event in self._run(message):
                yield event

        except Exception:
            yield {
                "type": "token",
                "text": traceback.format_exc(),
            }
