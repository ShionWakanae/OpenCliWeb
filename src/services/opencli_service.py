import time
import traceback
from openai import AsyncOpenAI
from utils.settings import settings
from utils.opencli_doctor import (
    evaluate_doctor_output,
    find_legacy_disconnected_profile,
    find_recovery_profile,
    parse_doctor_envelope,
    parse_profile_list,
)
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
        evaluation = None
        all_ok = False
        while True:
            # opencli doctor
            evaluation, error, raw_output = self._run_doctor()

            if error is not None:
                # opencli 自身报错（如 ok:false 信封）
                log(
                    f"[Service] opencli doctor failed: {error.get('message', '')}",
                    False,
                )
                code = error.get("code")
                if code:
                    log(f"[Service] opencli doctor error code: {code}", False)
                hint = error.get("hint") or error.get("help")
                if hint:
                    log(f"[Service] {hint}", False)
                log(
                    "[Service] opencli doctor failed, please check!",
                    False,
                )
                exit(1)

            if evaluation is None:
                log(
                    "[Service] opencli doctor output could not be parsed, please check!",
                    False,
                )
                exit(1)

            # 三项检查：Daemon / Extension / Connectivity
            self._log_doctor_evaluation(evaluation)
            all_ok = evaluation.all_ok

            if all_ok:
                break
            if check_profile_connect:
                break

            check_profile_connect = True
            profile_label = self._pick_recovery_profile(evaluation, raw_output)
            if profile_label:
                log(f"[Service] try use profile `{profile_label}` ...")
                r = self._cli_tool._execute_any_command(
                    f"opencli profile use {profile_label}"
                )
                if not r.success:
                    log(self._command_error(r), False)
                    log(
                        "[Service] opencli profile use failed, please check!",
                        False,
                    )
                    break
                else:
                    log(r.stdout.strip())
            time.sleep(2)
            log("[Service] Let's wait a minute.")
            time.sleep(2)
            log("[Service] Not really one minute, I mean maybe a few seconds...")
            time.sleep(2)
            log("[Service] OK try again...")

        # 如果有任何检查失败，则退出
        if not all_ok:
            failed = ", ".join(evaluation.failed_checks) if evaluation else ""
            log(
                "[Service] opencli doctor validation failed"
                + (f": {failed}" if failed else ""),
                False,
            )
            if evaluation is not None:
                log(self._format_doctor_summary(evaluation), False)
            exit(1)

        log("[Service] opencli doctor passed")

    def _run_doctor(self):
        """执行 opencli doctor 并解析输出。

        返回 (evaluation, error, raw_output)：
          - evaluation: 解析出的自检结果（新版 JSON 信封 / 旧版文本）
          - error:     opencli 自身报错时的错误字典（ok:false 信封）
          - raw_output: 原始输出，供旧版文本解析兜底使用
        """
        r = self._cli_tool._execute_any_command("opencli doctor")
        raw_output = r.stdout or ""

        if not r.success:
            # opencli 失败时错误信封(JSON)打在 stdout 上，stderr 可能为空
            _, error = parse_doctor_envelope(raw_output)
            if error is None:
                detail = (r.error or raw_output or "").strip()
                error = {"message": detail or "opencli doctor failed"}
            return None, error, raw_output

        evaluation, error = evaluate_doctor_output(raw_output)
        return evaluation, error, raw_output

    def _command_error(self, result) -> str:
        """取一条可读的错误描述。

        opencli 失败时把错误信封(JSON)打在 stdout 上，stderr 往往为空，
        所以这里要同时考虑 stdout。
        """
        return (result.stderr or result.stdout or result.error or "").strip()

    def _log_doctor_evaluation(self, evaluation):
        """打印 doctor 自检结果。

        issues 只作为警告展示，不阻断启动；
        只有 daemon / extension / connectivity 三项失败才会阻断。
        """
        for component, status in evaluation.checks.items():
            if status:
                log(f"[Service] opencli ✓ {component}: [green]OK[/]", False)
            else:
                log(f"[Service] opencli ✗ {component}: [red]FAILED[/]", False)

        details = evaluation.details

        versions = []
        if details.get("cliVersion"):
            versions.append(f"cli v{details['cliVersion']}")
        if details.get("daemonVersion"):
            versions.append(f"daemon v{details['daemonVersion']}")
        if details.get("extensionVersion"):
            versions.append(f"extension v{details['extensionVersion']}")
        if versions:
            log(f"[Service] opencli version: {', '.join(versions)}", False)

        duration_ms = details.get("connectivityDurationMs")
        if duration_ms is not None and evaluation.checks.get("Connectivity"):
            log(f"[Service] opencli connectivity: {duration_ms}ms", False)

        # 警告信息，不影响启动
        warnings = []
        if details.get("daemonFlaky"):
            warnings.append("daemon is unstable")
        if details.get("daemonStale"):
            warnings.append("daemon version is stale")
        if details.get("extensionFlaky"):
            warnings.append("extension connection is unstable")
        if details.get("extensionOutdated"):
            current = details.get("extensionVersion")
            latest = details.get("latestExtensionVersion")
            if current and latest:
                warnings.append(f"extension update available: v{current} → v{latest}")
            else:
                warnings.append("extension is outdated")
        for warning in warnings:
            log(f"[Service] opencli ⚠ {warning}", False)

        for issue in evaluation.issues:
            log(f"[Service] opencli ⚠ {issue}", False)

    def _format_doctor_summary(self, evaluation) -> str:
        """doctor 未通过时的可读摘要。

        新版输出是 JSON，直接打印原文很难读，这里换成可读的摘要。
        """
        lines = []
        for component, status in evaluation.checks.items():
            lines.append(f"  {component:<13}: {'OK' if status else 'FAILED'}")

        details = evaluation.details
        versions = []
        if details.get("cliVersion"):
            versions.append(f"cli v{details['cliVersion']}")
        if details.get("daemonVersion"):
            versions.append(f"daemon v{details['daemonVersion']}")
        if details.get("extensionVersion"):
            versions.append(f"extension v{details['extensionVersion']}")
        if versions:
            lines.append(f"  {'version':<13}: {', '.join(versions)}")

        for issue in evaluation.issues:
            lines.append(f"  issue         : {issue}")

        return "\n".join(lines)

    def _pick_recovery_profile(self, evaluation, raw_output):
        """挑一个用于恢复的 profile 名。

        - 新版 JSON 信封：`opencli profile use` 只是修改默认 profile 指向，
          不会拉起浏览器，所以应把默认指向一个**仍然在线**的 profile
          （对应 doctor 的 stale default / 多 profile 场景）。
        - 旧版文本格式：沿用旧行为，使用文本中提示的 profile 名。
        """
        if evaluation.source == "legacy":
            return find_legacy_disconnected_profile(raw_output)

        r = self._cli_tool._execute_any_command("opencli profile list")
        if not r.success:
            log(
                f"[Service] opencli profile list failed: {self._command_error(r)}",
                False,
            )
            return None

        profiles = parse_profile_list(r.stdout)
        profile = find_recovery_profile(profiles)
        return profile.label if profile else None

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
        debug_events = None
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
                elif event["type"] == "debug":
                    debug_events = event
                yield event

            # no token, no answer
            if not debug_events:
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
