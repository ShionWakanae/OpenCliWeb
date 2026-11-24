"""
opencli 2.x 输出协议的统一解析层。

opencli 升级到 2.x 之后，CLI 的输出分成两种形态：

1. **信封格式**（核心命令 `doctor` / `profile` / `auth`，以及 `-f json`）::

    成功: {"ok": true,  "data": {...}}
    失败: {"ok": false, "error": {"code": ..., "message": ..., "exitCode": ..., "hint": ...}}

2. **裸 payload**（`-f yaml` / `-f table` / `--help`）：直接输出格式化后的内容，不带信封。

必须遵守的几条约定（都是实测 opencli 2.0.3 得到的结论）：

- **失败信封永远打在 stdout 上，stderr 恒为空。**
  所以只看 stderr 会把真实错误信息（Unknown command / NOT_FOUND / 超时 ...）全部丢掉。
- **失败时无论请求哪种 `-f` 格式，返回的都是 JSON 信封。**
  所以失败判定必须看 JSON 结构，不能依赖请求的输出格式。
- 信封里的 `error.exitCode` 与进程退出码一致，但**以信封结构为准**更可靠：
  退出码可能被调用方包装/截断，而信封是 opencli 自己写出的结论。
- 裸 payload 里也可能出现 `ok` 字段，所以识别信封要求同时具备
  `ok` 与 `data` / `error` 之一，避免把普通站点数据误判成信封。

本模块只关心「怎么读 opencli 的输出」，不关心具体是哪个命令。
"""

import json
from typing import Any

import yaml

# 信封标识：ok 键 + data/error 键之一
_ENVELOPE_OK_KEY = "ok"
_ENVELOPE_PAYLOAD_KEYS = ("data", "error")

# 错误文案前缀
ERROR_PREFIX = "opencli 错误"
HINT_PREFIX = "提示"


def loads_object(text: str) -> dict | None:
    """从文本里尽力提取一个 JSON 对象。

    stdout 里可能混有日志行，所以整段解析失败时，退化成
    「从第一个 ``{`` 开始，用 raw_decode 解析第一个 JSON 值」，
    这样既能容忍前后噪声，也不会被消息里的 ``}`` 带偏。
    """
    text = (text or "").strip()
    if not text:
        return None

    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    start = text.find("{")
    if start == -1:
        return None

    try:
        payload, _ = json.JSONDecoder().raw_decode(text, start)
    except Exception:
        return None

    return payload if isinstance(payload, dict) else None


def detect_envelope(text: str) -> dict | None:
    """判断文本是不是 opencli 的 JSON 信封，是则返回该信封，否则返回 None。"""
    payload = loads_object(text)
    if payload is None:
        return None

    if _ENVELOPE_OK_KEY not in payload:
        return None

    # 信封一定带 data 或 error 之一，避免把普通站点数据误判成信封
    if not any(key in payload for key in _ENVELOPE_PAYLOAD_KEYS):
        return None

    return payload


def parse_envelope(text: str) -> tuple[bool | None, Any, dict | None]:
    """解析 opencli 的 JSON 信封。

    返回 ``(ok, data, error)``：

    - 信封 ok=true  -> ``(True, <data>, None)``
    - 信封 ok=false -> ``(False, None, <error dict>)``
    - 不是信封      -> ``(None, None, None)``
    """
    envelope = detect_envelope(text)
    if envelope is None:
        return None, None, None

    ok = envelope.get(_ENVELOPE_OK_KEY)

    if ok is False:
        error = envelope.get("error")
        if isinstance(error, dict):
            return False, None, error
        if error:
            return False, None, {"message": str(error)}
        return False, None, {"message": "unknown error"}

    if ok is True:
        data = envelope.get("data")
        return True, ({} if data is None else data), None

    # 有 ok 键但值不是布尔：按 data 存在与否兜底
    if "error" in envelope:
        error = envelope.get("error")
        if isinstance(error, dict):
            return False, None, error
        return False, None, {"message": str(error) if error else "unknown error"}

    data = envelope.get("data")
    return True, ({} if data is None else data), None


def format_error(error: Any) -> str:
    """把错误信封里的 error 对象转成人读文本。

    形如::

        opencli 错误 [NOT_FOUND]: No recommended projects found on Gitee Explore
        提示: Gitee may be blocking this request or the page structure changed

    没有 code / hint 时自动省略对应部分。
    """
    if error is None:
        return ""

    if isinstance(error, str):
        message = error.strip()
        return f"{ERROR_PREFIX}: {message}" if message else ""

    if not isinstance(error, dict):
        return f"{ERROR_PREFIX}: {error}"

    code = str(error.get("code") or "").strip()
    message = str(error.get("message") or "").strip()
    hint = str(error.get("hint") or error.get("help") or "").strip()

    if code and message:
        headline = f"{ERROR_PREFIX} [{code}]: {message}"
    elif code:
        headline = f"{ERROR_PREFIX} [{code}]"
    elif message:
        headline = f"{ERROR_PREFIX}: {message}"
    else:
        headline = ERROR_PREFIX

    if hint:
        return f"{headline}\n{HINT_PREFIX}: {hint}"

    return headline


def describe_error(
    envelope_error: dict | None,
    stdout: str = "",
    stderr: str = "",
    returncode: int | None = None,
) -> tuple[str, str, str]:
    """生成一条可读的错误描述。

    返回 ``(error, code, hint)``：

    - error:  给人看的错误文本
    - code:   错误码（可能为空）
    - hint:   提示（可能为空）
    """
    code = ""
    hint = ""

    if isinstance(envelope_error, dict):
        code = str(envelope_error.get("code") or "").strip()
        hint = str(
            envelope_error.get("hint") or envelope_error.get("help") or ""
        ).strip()
        error = format_error(envelope_error)
        if error:
            return error, code, hint

    # 没有信封：退化到 stderr / stdout
    stderr_text = (stderr or "").strip()
    if stderr_text:
        return stderr_text, code, hint

    stdout_text = (stdout or "").strip()
    if stdout_text:
        # stdout 可能本身就是一段 JSON（比如被截断的信封），尽量提取 message
        payload = loads_object(stdout_text)
        if payload is not None:
            inner = payload.get("error")
            if isinstance(inner, dict):
                code = code or str(inner.get("code") or "").strip()
                hint = hint or str(
                    inner.get("hint") or inner.get("help") or ""
                ).strip()
                return format_error(inner), code, hint
            message = payload.get("message") or payload.get("error")
            if message:
                return f"{ERROR_PREFIX}: {message}", code, hint
        return stdout_text, code, hint

    if returncode is not None:
        return f"{ERROR_PREFIX}: 命令执行失败（退出码 {returncode}）", code, hint

    return f"{ERROR_PREFIX}: 命令执行失败", code, hint


def parse_payload(text: str, format_output: str = "") -> Any:
    """按请求的格式解析成功时的输出内容。

    - 若输出是信封（``{"ok":true,"data":...}``），返回解包后的 ``data``。
    - 否则按 ``format_output`` 解析（json / yaml），解析失败返回 None。
    """
    fmt = (format_output or "").lower().strip()

    ok, data, _ = parse_envelope(text)
    if ok is True:
        return data

    if not fmt or not (text or "").strip():
        return None

    if fmt == "json":
        return json.loads(text)
    if fmt == "yaml":
        return yaml.safe_load(text)

    return None
