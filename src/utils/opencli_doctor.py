"""
解析 `opencli doctor` 的输出。

opencli 2.x 起，`opencli doctor` 不再输出人类可读的文本，只输出 JSON 信封：

    {"ok": true, "data": { ...DoctorReport... }}

失败时（例如 CLI 自身异常）输出错误信封，并设置非零退出码：

    {"ok": false, "error": {"code": ..., "message": ..., "exitCode": ..., "hint": ...}}

注意：
- doctor 即使发现问题（issues 非空）也仍然是 ok=true / exit 0，
  健康与否要看 daemonRunning / extensionConnected / connectivity.ok 三个标志位。
- 错误信封打在 **stdout** 上，stderr 往往为空，解析时不要只看 stderr。
- 2.x 里文本渲染器 `renderBrowserDoctorReport` 仍然存在，但已不再挂载到
  doctor 命令上，所以文本解析只对 opencli 1.x 有意义，这里保留兼容解析。
"""

import json
import re
from dataclasses import dataclass, field

# 旧版文本格式中需要检查的三个关键部分
LEGACY_CHECK_PATTERNS = {
    "Daemon": "[OK] Daemon: running",
    "Extension": "[OK] Extension: connected",
    "Connectivity": "[OK] Connectivity: connected",
}

# 旧版文本中未连接的 profile 提示
LEGACY_PROFILE_PATTERN = r'Browser profile "([^"]+)" is not connected'


@dataclass
class DoctorEvaluation:
    """doctor 自检结果的统一表示（不区分新旧输出格式）。"""

    checks: dict[str, bool] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    # "json" | "legacy"
    source: str = ""

    @property
    def all_ok(self) -> bool:
        return all(self.checks.values()) if self.checks else False

    @property
    def failed_checks(self) -> list[str]:
        return [name for name, ok in self.checks.items() if not ok]


@dataclass
class ProfileEntry:
    """`opencli profile list` 中的一个 profile。"""

    context_id: str
    alias: str | None = None
    default: bool = False
    connected: bool = False
    extension_version: str | None = None

    @property
    def label(self) -> str:
        """用于 `opencli profile use` 的参数：优先用 alias，其次用 contextId。

        opencli 的 `profile use` 同时接受 alias 和 contextId。
        """
        return self.alias or self.context_id


def _loads_object(text: str) -> dict | None:
    """从文本里尽力提取一个 JSON 对象。"""
    text = (text or "").strip()
    if not text:
        return None

    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    # stdout 里可能混有日志行，退化成截取最外层花括号
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        payload = json.loads(text[start : end + 1])
    except Exception:
        return None

    return payload if isinstance(payload, dict) else None


def parse_doctor_envelope(raw: str) -> tuple[dict | None, dict | None]:
    """解析 doctor 的 JSON 信封。

    返回 (report, error)：
      - ok:true  -> (data, None)
      - ok:false -> (None, error)
      - 非 JSON  -> (None, None)，交给旧版文本解析
    """
    payload = _loads_object(raw)
    if payload is None:
        return None, None

    ok = payload.get("ok")

    if ok is False:
        error = payload.get("error")
        if isinstance(error, dict):
            return None, error
        return None, {"message": str(error) if error else "unknown error"}

    if ok is True:
        data = payload.get("data")
        return (data if isinstance(data, dict) else {}), None

    # 信封缺少 ok 字段但带 data：仍按 report 处理，
    # 否则会误落到旧版文本解析，把一份正常的 JSON 当成失败。
    data = payload.get("data")
    if isinstance(data, dict):
        return data, None

    return None, None


def _format_issue(item) -> str:
    """把 issues 里的单条内容转成可读文本。

    上游 DoctorReport.issues 是 string[]，但个别情况下可能是对象，
    这时取 message / code，而不是直接 str() 出一个 Python dict。
    """
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        message = item.get("message") or ""
        code = item.get("code") or ""
        if message and code and code not in message:
            return f"{message} ({code})"
        return message or code or json.dumps(item, ensure_ascii=False)
    return str(item)


def evaluate_doctor_report(report: dict) -> DoctorEvaluation:
    """把新版的 DoctorReport 转成统一的三项检查结果。"""
    connectivity = report.get("connectivity")
    if not isinstance(connectivity, dict):
        connectivity = {}

    checks = {
        "Daemon": bool(report.get("daemonRunning")),
        "Extension": bool(report.get("extensionConnected")),
        "Connectivity": bool(connectivity.get("ok")),
    }

    issues = report.get("issues")
    if not isinstance(issues, list):
        issues = []

    details = {
        "cliVersion": report.get("cliVersion"),
        "daemonVersion": report.get("daemonVersion"),
        "extensionVersion": report.get("extensionVersion"),
        "latestExtensionVersion": report.get("latestExtensionVersion"),
        "daemonFlaky": bool(report.get("daemonFlaky")),
        "daemonStale": bool(report.get("daemonStale")),
        "extensionFlaky": bool(report.get("extensionFlaky")),
        "extensionOutdated": bool(report.get("extensionOutdated")),
        "connectivityDurationMs": connectivity.get("durationMs"),
        "connectivityError": connectivity.get("error"),
        "profiles": report.get("profiles") or [],
        "adapterShadows": report.get("adapterShadows") or [],
    }

    return DoctorEvaluation(
        checks=checks,
        issues=[_format_issue(item) for item in issues],
        details=details,
        source="json",
    )


def _parse_legacy_issues(text: str) -> list[str]:
    """提取旧版文本里 "Issues:" 段落的内容。"""
    issues: list[str] = []
    in_issues = False

    for line in text.splitlines():
        stripped = line.strip()
        if not in_issues:
            if stripped.rstrip(":").lower() == "issues":
                in_issues = True
            continue

        if not stripped:
            continue
        if stripped.startswith(("•", "-", "*")):
            stripped = stripped.lstrip("•-* ")
        issues.append(stripped)

    return issues


def evaluate_legacy_doctor(output: str) -> DoctorEvaluation:
    """旧版 opencli（文本输出）的检查逻辑。"""
    text = output or ""

    checks = {
        name: pattern in text for name, pattern in LEGACY_CHECK_PATTERNS.items()
    }

    issues = _parse_legacy_issues(text)

    match = re.search(LEGACY_PROFILE_PATTERN, text)
    if match:
        issues.append(f'Browser profile "{match.group(1)}" is not connected')

    return DoctorEvaluation(
        checks=checks,
        issues=issues,
        details={},
        source="legacy",
    )


def evaluate_doctor_output(raw: str) -> tuple[DoctorEvaluation | None, dict | None]:
    """解析 doctor 的原始输出。

    返回 (evaluation, error)：
      - 新版 JSON   -> (evaluation, None)
      - 旧版文本    -> (evaluation, None)
      - ok:false    -> (None, error)
      - 完全无法识别 -> (None, None)
    """
    report, error = parse_doctor_envelope(raw)
    if error is not None:
        return None, error
    if report is not None:
        return evaluate_doctor_report(report), None

    if (raw or "").strip():
        return evaluate_legacy_doctor(raw), None

    return None, None


def parse_profile_list(raw: str) -> list[ProfileEntry]:
    """解析 `opencli profile list` 的 JSON 输出。

    返回所有 profile（含未连接的），未连接的 profile 其 connected 为 False。
    """
    payload = _loads_object(raw)
    if payload is None:
        return []

    data = payload.get("data")
    if not isinstance(data, dict):
        return []

    profiles: list[ProfileEntry] = []
    for item in data.get("profiles") or []:
        if not isinstance(item, dict):
            continue

        context_id = item.get("contextId")
        if not context_id:
            continue

        alias = item.get("alias")
        profiles.append(
            ProfileEntry(
                context_id=context_id,
                alias=alias if isinstance(alias, str) and alias else None,
                default=bool(item.get("default")),
                connected=bool(item.get("connected")),
                extension_version=item.get("extensionVersion"),
            )
        )

    return profiles


def find_recovery_profile(profiles: list[ProfileEntry]) -> ProfileEntry | None:
    """挑一个用于恢复的 profile。

    新版 opencli 的 profile 只在配置里记录 contextId 并指向 daemon，
    `opencli profile use` 并不会拉起浏览器，所以正确的恢复动作是
    把默认 profile 指向一个**仍然在线**的 profile。

    这也正是 opencli doctor 自己给出的建议：
        "Refresh it with: opencli profile list, then opencli profile use <name>."

    返回 None 表示不需要切换（默认 profile 仍在线，或没有任何在线 profile）。
    """
    connected = [p for p in profiles if p.connected]
    if not connected:
        return None

    default = next((p for p in profiles if p.default), None)
    if default is not None and default.connected:
        # 默认 profile 还在线，不用动
        return None

    return connected[0]


def find_legacy_disconnected_profile(output: str) -> str | None:
    """旧版文本格式里未连接的 profile 名称。"""
    match = re.search(LEGACY_PROFILE_PATTERN, output or "")
    return match.group(1) if match else None
