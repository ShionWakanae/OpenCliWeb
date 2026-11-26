"""版本号文本的显示格式化。

`node --version` 的输出和 opencli doctor 报告里的版本号可能带 ``v`` 前缀，
这里统一去掉，只保留数字部分，便于终端着色和阅读。

放在独立模块里是为了保持纯函数、无副作用，方便直接单测；
否则从 services.opencli_service 导入会触发启动时的环境检查。
"""


def clean_version(value) -> str:
    """去掉首尾空白和开头的 v/V，只保留版本数字部分。"""
    text = str(value).strip() if value is not None else ""
    if text[:1] in ("v", "V"):
        text = text[1:]
    return text


def format_versions(details: dict) -> str:
    """把 doctor details 里的 cli / daemon / extension 版本拼成一行。"""
    versions = []
    for key, label in (
        ("cliVersion", "cli"),
        ("daemonVersion", "daemon"),
        ("extensionVersion", "extension"),
    ):
        version = clean_version(details.get(key))
        if version:
            versions.append(f"{label} {version}")
    return ", ".join(versions)
