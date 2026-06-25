import time
import traceback
import re
from openai import AsyncOpenAI
from utils.settings import settings
from opencli.IntelligentAgent import IntelligentCLIAgent
from opencli.OpenCLITool import OpenCLITool
from utils.logger import logger

log = logger.log


def get_error_message(e: Exception) -> str:
    # OpenAI SDK
    if hasattr(e, "body"):
        try:
            return e.body["error"]["message"]
        except Exception:
            pass

    # requests
    if hasattr(e, "response"):
        try:
            data = e.response.json()
            if "error" in data:
                return data["error"]
        except Exception:
            pass

    if str(e).strip() != "":
        return str(e)
    return f"{e.__class__.__module__}.{e.__class__.__name__}"


def create_agent(
    base_url="https://api.openai.com/v1",
    api_key="",
    model="gpt-4o-mini",
    opencli_profile=None,
    think=False,
    verbose=False,
    on_execute=None,
):
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    tool = OpenCLITool(profile=opencli_profile, verbose=verbose, on_execute=on_execute)
    return IntelligentCLIAgent(
        client=client,
        model=model,
        opencli_tool=tool,
        think=think,
        verbose=verbose,
    )


class OpenCLIService:
    def __init__(
        self,
    ):
        log("[Service] init...")
        self._cli_tool = OpenCLITool()

        # check node.js version
        r = self._cli_tool._execute_any_command("node --version")
        if not r.success:
            log(r.error, False)
            log(
                "[Service] node.js check failed, please install node.js >= 20",
                False,
            )
            exit(1)
        else:
            log(f"[Service] node.js version: {r.stdout.strip()}")

        # check opencli version
        r = self._cli_tool._execute_opencli_command("--version")
        if not r.success:
            log(r.error, False)
            log(
                "[Service] opencli check failed, please 'npm install -g @jackwener/opencli'",
                False,
            )
            exit(1)
        else:
            log(f"[Service] opencli version: {r.stdout.strip()}")

        # 记录是否连接profile
        check_profile_connect = False
        while True:
            # opencli doctor
            r = self._cli_tool._execute_any_command("opencli doctor")
            if not r.success:
                log(r.error, False)
                log(
                    "[Service] opencli doctor failed, please check!",
                    False,
                )
                exit(1)
            else:
                # 这里应该检查opencli doctor返回的：1)Daemon, 2)Extension, 3)Connectivity
                output = r.stdout.strip()
                # 需要检查的三个关键部分
                checks = {
                    "Daemon": "[OK] Daemon: running" in output,
                    "Extension": "[OK] Extension: connected" in output,
                    "Connectivity": "[OK] Connectivity: connected" in output,
                }

                all_ok = True
                for component, status in checks.items():
                    if status:
                        log(f"[Service] opencli ✓ {component}: [green]OK[/]", False)
                    else:
                        log(f"[Service] opencli ✗ {component}: [red]FAILED[/]", False)
                        all_ok = False

                if all_ok:
                    break
                if check_profile_connect:
                    break

                check_profile_connect = True
                pattern2 = r'Browser profile "([^"]+)" is not connected'
                match2 = re.search(pattern2, output)
                if match2:
                    profile_id = match2.group(1)
                    log(f"[Service] try use profile `{profile_id}` ...")
                    r = self._cli_tool._execute_any_command(
                        f"opencli profile use {profile_id}"
                    )
                    if not r.success:
                        log(r.error, False)
                        log(
                            "[Service] opencli profile use failed, please check!",
                            False,
                        )
                        break
                    else:
                        log(r.stdout.strip())

        # 如果有任何检查失败，则退出
        if not all_ok:
            log("[Service] opencli doctor validation failed", False)
            print(output)
            print()
            exit(1)

        log("[Service] opencli doctor passed")

    async def stream_answer(
        self,
        question,
        think=False,
        verbose=False,
    ):
        # events = []

        # def on_execute(event):
        #     events.append(event)
        log(f"[Service] LLM provider: {settings.llm_api_base}", False)
        agent = create_agent(
            base_url=settings.llm_api_base,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            think=think,
            verbose=verbose,
            # on_execute=on_execute,
        )

        total_start = time.perf_counter()
        first_token = False
        answer_start = total_start
        got_answer = False
        think_start = False
        think_end = False
        yield {
            "type": "trace",
            "stage": "开始",
            "message": "收到用户指令并开始处理……",
            "timing": 0,
        }
        try:
            async for event in agent.astream(question):
                if event["type"] == "token":
                    if event["text"]:
                        # handle <think></think> block as reasoning
                        if not think_start and "<think>" in event["text"].lower():
                            think_start = True
                        if think_start and not think_end:
                            event["type"] = "reasoning"
                            yield event
                            if "</think>" in event["text"].lower():
                                think_end = True
                            continue

                        got_answer = True
                        if not first_token:
                            first_token = True
                            answer_start = time.perf_counter()
                elif event["type"] == "tool":
                    # 工具调用，重置回答开始时间，适用于某些把推理过程输出到普通token中的模型。
                    answer_start = time.perf_counter()
                    got_answer = False
                yield event

            # no token, no answer
            if answer_start == total_start:
                answer_start = time.perf_counter()

            query_ms = round((answer_start - total_start) * 1000, 2)
            llm_ms = round((time.perf_counter() - answer_start) * 1000, 2)
            total_ms = round((time.perf_counter() - total_start) * 1000, 2)

            yield {
                "type": "debug",
                "query_ms": query_ms,
                "llm_ms": llm_ms,
                "total_ms": total_ms,
            }

            yield {
                "type": "status",
                "got_answer": got_answer,
                "source": "opencli",
            }

        except Exception as e:
            print(traceback.format_exc())
            error_message = get_error_message(e)
            yield {
                "type": "trace",
                "stage": "异常",
                "message": f"003 :: {error_message}",
                "timing": 0,
            }

            yield {
                "type": "token",
                "text": f"📛错误：{error_message}\n",
            }
            yield {
                "type": "status",
                "got_answer": False,
                "source": "error",
            }


service = OpenCLIService()
