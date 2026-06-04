import asyncio
import json
import traceback
from typing import Optional
from textwrap import dedent
from openai import AsyncOpenAI
from opencli.OpenCLITool import OpenCLITool
from collections import defaultdict
from utils.logger import logger

log = logger.log


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
            log(f"[Agent] loaded {len(self.tools)} tools")
            for t in self.tools:
                log(f"- {t['function']['name']}")

    # prompt
    def _get_system_prompt(
        self,
    ):
        """获取系统提示词"""
        return dedent("""\
            你是一个智能助手，能够使用 OpenCLI 工具来操作各种网站

            ## 可用工具：
            - **get_today_date**: 获取当天日期
            - **sites_list**: 列出所有可用的网站
            - **site_cmds_list**: 列出单个网站的所有可用命令
            - **site_cmd_help**: 获取单个网站的单个命令详细帮助
            - **opencli_execute**: 执行任意完整命令字符串

            ## 日期规则：
            1. 
            如果用户输入了明确的日期，则不必调用 get_today_date

            2，
            如果用户提到类似'今天'，'明天'等不确定的日期，则调用 get_today_date
            并计算出用户真实希望的日期字符串，供后续命令使用

            3，
            如果用户输入信息中没有日期内容，但发现在后续命令中需要日期，则调用 get_today_date
            并使用当天日期

            ## 网站和命令选择规则：
            1.
            如果用户使用标准网站名：
            bilibili, zhihu, github

            直接：
            site_cmds_list(site)

            2.
            如果用户使用别名、简称、中文名称：
            B站, 知乎, 新浪财经, 微博, 小红书

            先：
            sites_list()

            找到最匹配的网站名后：
            site_cmds_list(site)

            3.
            禁止猜测网站名称
            如果无法确认，必须先 list 所有可用的网站名称

            4 列出网站全部命令后:
            site_cmd_help(site, cmd)

            5 拼接出完整命令字符串后：
            opencli_execute(...)

            ## 规则：
            不要拼 opencli
            不要拼 cmd
            不要加 -f 某格式

            ## 禁止：
            - 不要重复调用帮助
            - 同样的命令超过3次返回错误，停止工具调用，禁止继续重复

            ## 输出格式
            - 返回数据后用友好的方式向用户展示
            - 不要隐藏超链接
            - 如果工具返回错误，解释可能的原因并给出建议
            """)

    # internal
    async def _run(
        self,
        message,
    ):
        tools_called = defaultdict(int)
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
        is_answering = False
        MAX_TOOL = 99
        loop_count = 0
        for _ in range(MAX_TOOL):
            loop_count += 1
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
            reasoning = ""
            tool_calls = {}
            try:
                async for chunk in stream:
                    # usage chunk
                    if chunk.usage:
                        yield {
                            "type": "usage",
                            "usage": chunk.usage.model_dump(),
                            "model": chunk.model.replace(".gguf", ""),
                        }
                        continue

                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta

                    tmp_reasoning = ""
                    if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                        tmp_reasoning = delta.reasoning_content
                    if hasattr(delta, "reasoning") and delta.reasoning:
                        tmp_reasoning = delta.reasoning

                    if tmp_reasoning:
                        reasoning += tmp_reasoning
                        yield {
                            "type": "reasoning",
                            "text": tmp_reasoning,
                        }
                    # 普通文本
                    if hasattr(delta, "content") and delta.content:
                        content += delta.content
                        yield {
                            "type": "token",
                            "text": delta.content,
                        }
                        if not is_answering:
                            is_answering = True

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
            except Exception as e:
                if "Failed to parse input" in str(e):
                    log(f"error : {e}")
                    yield {
                        "type": "trace",
                        "stage": "异常",
                        "message": f"({content}) : {e}",
                        "timing": 0,
                    }
                    continue
                else:
                    raise

            # finish
            if not tool_calls:
                if any(
                    keyword in content
                    for keyword in ["Failed to parse input", "Traceback", "APIError"]
                ):
                    log("error in content!")
                    yield {
                        "type": "trace",
                        "stage": "异常",
                        "message": content,
                        "timing": 0,
                    }
                    yield {
                        "type": "token",
                        "text": "输出结果中包含了异常信息！",
                    }
                else:
                    yield {
                        "type": "done",
                        "text": content,
                    }
                return

            # assistant（只追加一次）
            messages.append(
                {
                    "role": "assistant",
                    "reasoning": reasoning,
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
                    "tool_name": f"({loop_count}) {name}",
                    "message": name,
                    "kwargs": args,
                    "text_content": "",
                }
                full_name = name + json.dumps(args, sort_keys=True)
                tools_called[full_name] += 1
                if tools_called[full_name] > 3:
                    print("same tool and args over 3 times !!!")
                    yield {
                        "type": "trace",
                        "stage": "异常",
                        "message": "工具调用循环溢出！完全同样工具和参数调用次数超过3次。",
                        "timing": 0,
                    }
                    return

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
                    "tool_name": f"({loop_count}) {name}",
                    "message": name,
                    "kwargs": args,
                    "text_content": f"({len(text)}) {text}",
                }

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": text,
                    }
                )

        print("tool loop overflow !!!")
        yield {
            "type": "trace",
            "stage": "异常",
            "message": "工具调用循环溢出！在最终结果生成前，工具调用次数已经过多。",
            "timing": 0,
        }

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
        async for event in self._run(message):
            yield event
