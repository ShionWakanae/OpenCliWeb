import time
import traceback
from openai import AsyncOpenAI
from utils.settings import settings
from opencli.IntelligentAgent import IntelligentCLIAgent
from opencli.OpenCLITool import OpenCLITool
from utils.logger import logger

log = logger.log


def create_agent(
    base_url="https://api.openai.com/v1",
    api_key="",
    model="gpt-4o-mini",
    opencli_profile=None,
    verbose=False,
    on_execute=None,
):
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    tool = OpenCLITool(profile=opencli_profile, verbose=verbose, on_execute=on_execute)
    return IntelligentCLIAgent(
        client=client,
        model=model,
        opencli_tool=tool,
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

        # opencli doctor
        r = self._cli_tool._execute_opencli_command("doctor")
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

            # 记录检查结果
            all_ok = True
            for component, status in checks.items():
                if status:
                    log(f"[Service] opencli {component}: OK ✓")
                else:
                    # log(f"[Service] ✗ {component}: FAILED", False)
                    all_ok = False

            # 如果有任何检查失败，则退出
            if not all_ok:
                log("[Service] opencli doctor validation failed", False)
                print(output)
                exit(1)

            log("[Service] opencli doctor passed")

    async def stream_answer(
        self,
        question,
        verbose=False,
    ):
        # events = []

        # def on_execute(event):
        #     events.append(event)
        log(f"[Service] Start LLM provider: {settings.llm_api_base}", False)
        agent = create_agent(
            base_url=settings.llm_api_base,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            verbose=verbose,
            # on_execute=on_execute,
        )

        total_start = time.perf_counter()
        first_token = False
        answer_start = total_start
        got_answer = False

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
                        got_answer = True
                        if not first_token:
                            first_token = True
                            answer_start = time.perf_counter()
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

        except Exception:
            yield {
                "type": "token",
                "text": traceback.format_exc(),
            }

            yield {
                "type": "status",
                "got_answer": True,
                "source": "error",
            }


service = OpenCLIService()
