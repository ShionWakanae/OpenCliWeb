import asyncio
import calendar
import json
import os
import time
import traceback
from datetime import date
from typing import Optional

import yaml
from openai import AsyncOpenAI

from opencli.OpenCLITool import OpenCLITool
from utils.logger import logger
from utils.settings import settings

log = logger.log


class IntelligentCLIAgent:
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        opencli_tool: Optional[OpenCLITool] = None,
        think=False,
        verbose=False,
    ):

        self.client = client
        self.model = model
        self.think = think
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
        today = date.today()
        today_date = today.strftime("%Y-%m-%d")
        current_time = time.strftime("%H:%M:%S")
        today_weekday = calendar.day_name[today.weekday()]  # 输出英文：Saturday
        return f"""
你是一个智能助手，能够使用工具来操作网站, 获取信息。

## 可用网站列表[site list]：
{self.opencli_tool.prompt}

## 可用工具：
- **site_help**: 列出单个网站的所有可用命令和参数
- **cmd_exec**: 执行单个网站命令的完整命令字符串

## 日期规则：
1. 
如果用户输入了明确的日期，则直接使用该日期

2，
如果用户提到类似'今天'，'明天'等不确定的日期，则使用当前日期计算出用户指定的日期
如果用户输入信息中没有日期内容，但发现在后续命令中需要日期，则使用当前日期
现在是: {today_date} {today_weekday} {current_time} , 这是实时获取的日期时间，是真实的，不是举例。

## 网站查询步骤：
1.
第一步: 确认网站(site)名称:
根据用户输入, 从[site list]中找到最匹配的名称
你只能操作[site list]中的网站(site)

2.
第二步: 取得网站支持的命令列表:
执行 site_help(site), 返回命令列表

3.
第三步: 执行命令:
你只能执行网站支持的命令
拼接出完整命令字符串后：
执行 cmd_exec(...)，返回执行结果

## 命令参数规则：
不要拼 opencli
不要拼 cmd
不要加 -f 某格式

## 禁止：
- 禁止调用工具获取不必要的数据: 仅尝试获取必要的数据
- 禁止编造数据: 仅使用调用工具取得的真实数据
- 禁止猜测指令参数: 必须先调用 site_help() 确认支持的命令和参数
- 禁止重复调用 site_help()
- 如果 cmd_exec() 返回正常数据: 禁止用相同的参数反复调用
- 如果 cmd_exec() 返回:出错 or 超时 or 没有数据, 并且尝试次数已经达到3次: 立即停止工具调用并提示用户

## 输出格式
- 使用语言`{settings.language}`回答用户
- 输出Markdown格式的链接
- 如果工具返回错误，解释可能的原因并给出建议
"""

    #     # prompt
    #     def _get_score_prompt(
    #         self,
    #         history,
    #         content,
    #     ):
    #         return f"""
    # 请审查以下推理过程：

    # 推理过程：
    # {history}

    # 最终结果：
    # {content}

    # 你需要找出之前推理中有没有问题，包括可能出现的逻辑漏洞，条件遗漏，数据错误，虚假信息等。
    # 1. 有问题则回答 "核验不通过: {{问题的简要描述}}。"
    # 2. 无问题则给前面推理打分（100分制）并回答 "核验通过: {{你打的分数}}分。"
    # """

    def _extract_xml_tool_call(self, content: str):
        """从文本中提取XML格式的工具调用"""
        import re

        # 匹配你的XML格式
        pattern = r"<tool_call>\s*<function=([^>]+)>\s*<parameter=([^>]+)>\s*([\s\S]*?)\s*</parameter>\s*</function>\s*</tool_call>"
        match = re.search(pattern, content)

        if not match:
            return None

        tool_name = match.group(1).strip()
        param_name = match.group(2).strip()
        param_value = match.group(3).strip()

        # 尝试解析参数为JSON或保持字符串
        try:
            args = json.loads(param_value)
        except:
            args = {param_name: param_value}

        return {"name": tool_name, "args": args}

    def _clean_xml_from_content(self, content: str):
        """从内容中移除XML调用标签"""
        import re

        pattern = r"<tool_call>.*?</tool_call>"
        cleaned = re.sub(pattern, "", content, flags=re.DOTALL)
        return cleaned.strip()

    # internal
    async def _run(
        self,
        message,
    ):
        total_start = time.perf_counter()
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
        all_ok = False
        content = ""
        MAX_TOOL = 99
        loop_count = 0
        extra_body = {}
        tool_stage_len = 0
        pp_stage_len = 0
        if not self.think:
            extra_body = {
                "chat_template_kwargs": {"enable_thinking": False},
                "enable_thinking": False,
                "thinking": {"type": "disabled"},
            }
        last_trace_time = time.perf_counter()
        for _ in range(MAX_TOOL):
            loop_count += 1
            if self.verbose:
                trace_timing = time.perf_counter() - last_trace_time
                last_trace_time = time.perf_counter()
                yield {
                    "type": "trace",
                    "stage": "轮次",
                    "message": f"({loop_count})",
                    "timing": trace_timing * 1000,
                }
            tool_count = 0
            pp_start = time.perf_counter()
            first_token = False
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
                temperature=0.1,
                stream=True,
                stream_options={"include_usage": True},
                extra_body=extra_body,
                max_tokens=8192,
            )

            content = ""
            reasoning = ""
            tool_calls = {}
            is_xml_tool = False
            try:
                async for chunk in stream:
                    if not first_token:
                        first_token = True
                        pp_stage_len += time.perf_counter() - pp_start
                    # usage chunk
                    if chunk.usage:
                        yield {
                            "type": "usage",
                            "usage": chunk.usage.model_dump(),
                            "model": os.path.basename(chunk.model).replace(".gguf", ""),
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
                        if is_xml_tool:
                            if delta.content.strip() == "</tool_call>":
                                is_xml_tool = False
                        else:
                            if delta.content.strip() == "<tool_call>":
                                is_xml_tool = True
                                yield {
                                    "type": "token",
                                    "text": "⭐",
                                }
                                continue
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

                    if (
                        not hasattr(delta, "reasoning_content")
                        and not hasattr(delta, "reasoning")
                        and not hasattr(delta, "content")
                        and not delta.tool_calls
                    ):
                        print("unknown delta:")
                        print(delta)
                if not first_token:
                    first_token = True
                    pp_stage_len += time.perf_counter() - pp_start
            except Exception as e:
                # 这里是一个特殊的处理，原因不明，可能是聊天模板的问题，可跳过此轮而不是直接抛出异常。
                if "Failed to parse input" in str(
                    e
                ) or "does not match the expected peg-native format" in str(e):
                    print(f"error : {str(e)[:100]}")
                    if self.verbose:
                        print(traceback.format_exc())
                    yield {
                        "type": "trace",
                        "stage": "异常",
                        "message": f"001 :: {str(e)[:100]} :: {content[:-60]}",
                        "timing": 0,
                    }
                else:
                    raise

            # finish one round
            # check XML tool call in content
            if not tool_calls and content.strip():
                # 检查是否包含XML格式的工具调用
                xml_tool_call = self._extract_xml_tool_call(content)
                if xml_tool_call:
                    # 有XML工具调用，需要处理
                    tool_name = xml_tool_call["name"]
                    tool_args = xml_tool_call["args"]

                    # 构造一个模拟的tool_call结构，复用现有逻辑
                    tool_calls = {
                        0: {
                            "id": f"xml_call_{loop_count}",
                            "name": tool_name,
                            "args": json.dumps(tool_args)
                            if isinstance(tool_args, dict)
                            else tool_args,
                        }
                    }
                    # 从content中移除XML调用部分，只保留纯文本
                    content = self._clean_xml_from_content(content)
                    # 继续执行后续的工具调用逻辑

            # check tool calls
            if not tool_calls:
                if content.strip() == "" and reasoning.strip() == "":
                    yield {
                        "type": "trace",
                        "stage": "异常",
                        "message": "没有工具或思考或输出，结果为空！",
                        "timing": 0,
                    }
                if any(
                    keyword in content
                    for keyword in ["Failed to parse input", "Traceback", "APIError"]
                ):
                    log("error in content!")
                    yield {
                        "type": "trace",
                        "stage": "异常",
                        "message": "002 :: Error in content",
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
                all_ok = True
                break

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
            tool_start = time.perf_counter()
            for tc in tool_calls.values():
                tool_count += 1
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
                    "tool_name": f"({loop_count}.{tool_count}) {name}",
                    "message": name,
                    "kwargs": args,
                    "text_len": 0,
                    "text_content": "",
                }
                full_name = name + json.dumps(args, sort_keys=True)
                self.opencli_tool.tools_called[full_name] += 1
                if self.opencli_tool.tools_called[full_name] >= 5:
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

                # text = json.dumps(result, ensure_ascii=False, indent=2)
                text = yaml.safe_dump(
                    result, allow_unicode=True, default_flow_style=False
                )

                yield {
                    "type": "tool",
                    "stage": "←",
                    "tool_name": f"({loop_count}.{tool_count}) {name}",
                    "message": name,
                    "kwargs": args,
                    "text_len": len(text),
                    "text_content": text,
                }

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": text,
                    }
                )
            tool_stage_len += time.perf_counter() - tool_start

        total_end = time.perf_counter()
        query_ms = round(tool_stage_len * 1000, 2)
        pp_ms = round(pp_stage_len * 1000, 2)
        total_ms = round((total_end - total_start) * 1000, 2)
        llm_ms = round(total_ms - query_ms - pp_ms, 2)
        yield {
            "type": "debug",
            "query_ms": query_ms,
            "llm_ms": llm_ms,
            "total_ms": total_ms,
        }

        if not all_ok:
            print("tool loop overflow !!!")
            yield {
                "type": "trace",
                "stage": "异常",
                "message": "工具调用循环溢出！在最终结果生成前，工具调用次数过多。",
                "timing": 0,
            }
        #     return

        # yield {
        #     "type": "trace",
        #     "stage": "核验",
        #     "message": "检查最终答案的正确性……",
        #     "timing": 0,
        # }

        # messages.pop(0)
        # verify_messages = [
        #     {"role": "system", "content": "你是一个严格的审查者。"},
        #     {
        #         "role": "user",
        #         "content": self._get_score_prompt(messages, content),
        #     },
        # ]
        # # print(verify_messages)
        # stream = await self.client.chat.completions.create(
        #     model=self.model,
        #     messages=verify_messages,
        #     temperature=0.1,
        #     stream=True,
        #     stream_options={"include_usage": True},
        #     max_tokens=8192,
        # )
        # async for chunk in stream:
        #     # usage chunk
        #     if chunk.usage:
        #         yield {
        #             "type": "usage",
        #             "usage": chunk.usage.model_dump(),
        #             "model": chunk.model.replace(".gguf", ""),
        #         }
        #         continue

        #     if not chunk.choices:
        #         continue

        #     delta = chunk.choices[0].delta

        #     # tmp_reasoning = ""
        #     # if hasattr(delta, "reasoning_content") and delta.reasoning_content:
        #     #     tmp_reasoning = delta.reasoning_content
        #     # if hasattr(delta, "reasoning") and delta.reasoning:
        #     #     tmp_reasoning = delta.reasoning

        #     # if tmp_reasoning:
        #     #     yield {
        #     #         "type": "reasoning",
        #     #         "text": tmp_reasoning,
        #     #     }
        #     # 普通文本
        #     if hasattr(delta, "content") and delta.content:
        #         # print(f"token: {delta.content}")
        #         yield {
        #             "type": "token",
        #             "text": delta.content,
        #         }

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
