import subprocess
import json
import yaml
import shlex
import traceback
import re
from datetime import date
from textwrap import dedent
from dataclasses import dataclass
from typing import Any
from utils.logger import logger

log = logger.log


@dataclass
class CommandResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    data: Any = None
    data_format: str = ""
    command: str = ""
    error: str = ""

    def to_dict(self):
        payload = self.data
        if payload is None:
            payload = self.stdout

        return {
            "success": self.success,
            "data": payload,
            "error": self.error,
            "command": self.command,
        }


def process_toutiao_data(data):
    """专门处理头条数据"""
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "url" in item:
                # 清理 URL
                if "?" in item["url"]:
                    item["url"] = item["url"].split("?")[0]
    return data


def remove_fields(obj, fields_to_remove):
    """递归删除指定列表中的所有字段"""
    if isinstance(obj, dict):
        for field in fields_to_remove:
            if field in obj:
                del obj[field]
        for key, value in obj.items():
            obj[key] = remove_fields(value, fields_to_remove)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            obj[i] = remove_fields(item, fields_to_remove)
    return obj


def keep_fields(obj, fields_to_keep):
    """递归只保留指定列表中的字段，删除其他字段"""
    if isinstance(obj, dict):
        fields_to_delete = [key for key in obj.keys() if key not in fields_to_keep]
        for field in fields_to_delete:
            del obj[field]
        for key, value in obj.items():
            obj[key] = keep_fields(value, fields_to_keep)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            obj[i] = keep_fields(item, fields_to_keep)
    return obj


class OpenCLITool:
    def __init__(self, profile=None, verbose=False, timeout=90, on_execute=None):
        self.profile = profile
        self.verbose = verbose
        self.timeout = timeout
        self.on_execute = on_execute
        self.base_args = ["opencli"]
        if profile:
            self.base_args.extend(
                [
                    "--profile",
                    profile,
                ]
            )

        self._functions = {}
        self._schemas = {}
        self._sites = self._sites_list()
        self._register_all_tools()

    def _execute_any_command(
        self,
        command,
    ):

        cmd = [
            "cmd",
            "/c",
            *shlex.split(command),
        ]

        try:
            if self.verbose:
                print("[npm]", cmd)

            result = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                timeout=self.timeout,
                encoding="utf-8",
                text=True,
            )

            if result.returncode != 0:
                return CommandResult(
                    success=False,
                    command=" ".join(cmd),
                    stderr=result.stderr,
                    error=result.stderr,
                )

            data = None
            return CommandResult(
                success=True,
                command=" ".join(cmd),
                stdout=result.stdout,
                stderr=result.stderr,
                data=data,
            )

        except subprocess.TimeoutExpired:
            return CommandResult(
                success=False,
                error=f"命令执行超时({self.timeout}s)",
            )

        except Exception as e:
            if self.verbose:
                print(traceback.format_exc())

            return CommandResult(
                success=False,
                error=str(e),
            )

    def _execute_opencli_command(
        self,
        command,
        format_output="",
    ):
        format_output = format_output.lower()
        cmd = ["cmd", "/c", *self.base_args, *shlex.split(command)]
        if format_output and "-f" not in command and "--format" not in command:
            cmd.extend(["-f", format_output])

        if self.on_execute:
            self.on_execute(
                {
                    "type": "tool",
                    "message": command,
                    "stage": "execute",
                    "command": command,
                }
            )

        try:
            if self.verbose:
                log(f"[OpenCLI] {command}")

            result = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                timeout=self.timeout,
                encoding="utf-8",
                text=True,
            )

            if self.on_execute:
                self.on_execute(
                    {
                        "type": "tool",
                        "message": command,
                        "stage": "finished",
                        "command": command,
                        "success": result.returncode == 0,
                    }
                )

            if result.returncode != 0:
                return CommandResult(
                    success=False,
                    command=" ".join(cmd),
                    stderr=result.stderr,
                    error=result.stderr,
                )

            data = None
            if format_output and result.stdout.strip():
                try:
                    if format_output == "json":
                        data = json.loads(result.stdout)
                    if format_output == "yaml":
                        data = yaml.safe_load(result.stdout)

                except Exception:
                    if self.verbose:
                        print(traceback.format_exc())

            return CommandResult(
                success=True,
                command=" ".join(cmd),
                stdout=result.stdout,
                stderr=result.stderr,
                data=data,
                data_format=format_output,
            )

        except subprocess.TimeoutExpired:
            return CommandResult(
                success=False,
                error=f"命令执行超时({self.timeout}s)",
            )

        except Exception as e:
            if self.verbose:
                print(traceback.format_exc())

            return CommandResult(
                success=False,
                error=str(e),
            )

    # list sites
    def _sites_list(self):
        r = self._execute_opencli_command("list")
        if not r.success:
            log(r.error)
            raise Exception(r.error)

        sites = []
        for line in r.stdout.splitlines():
            if re.match(
                r"^  \S+\s*$",
                line,
            ):
                sites.append(line.strip())

        return sites

    # register
    def register(self, *, name, description, schema, fn):
        self._functions[name] = fn
        self._schemas[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": schema,
            },
        }

    # tools
    def _register_all_tools(self):

        # list cmds of one site
        def site_cmds_list(site):
            if site not in self._sites:
                return f"error: ({site}) is not a supported site name!"
            r = self._execute_opencli_command(f"{site} --help", format_output="yaml")
            if not r.success:
                return r.error
            if r.data:
                data = r.data
                fields = [
                    "site",
                    "commands",
                    "name",
                    "description",
                ]
                data = keep_fields(data, fields)

                # print(data)
                return data

            return r.stdout

        self.register(
            name="site_cmds_list",
            description=dedent("""\
                列出单个网站(site)支持的全部命令(cmds)
            """),
            schema={
                "type": "object",
                "properties": {"site": {"type": "string"}},
                "required": ["site"],
            },
            fn=site_cmds_list,
        )

        # help
        def site_cmd_help(site, cmd):
            if site not in self._sites:
                return f"error: ({site}) is not a supported site name!"
            r = self._execute_opencli_command(
                f"{site} {cmd} --help", format_output="yaml"
            )
            if not r.success:
                return r.error
            if r.data:
                data = r.data
                fields = [
                    "site",
                    "browser_common_options",
                    "common_options",
                    "next",
                    "columns",
                    "image_url",
                    "example",
                    "command",
                    "access",
                    "domain",
                    "browser",
                    "description",
                    "output_formats",
                ]
                data = remove_fields(data, fields)

                # result = r.data
                # if r.data_format == "json":
                #     data_str = json.dumps(r.data)
                # if r.data_format == "yaml":
                #     data_str = yaml.safe_dump(r.data)
                # else:
                #     data_str = r.stdout
                # print(f"{len(r.stdout)} -> {len(data_str)} -> {len(str(result))}")

                # print(data)
                return data

            return r.stdout

        self.register(
            name="site_cmd_help",
            description=dedent("""\
                查看单个网站(site)的单个命令(cmd)的帮助信息

                输入：
                网站名(site), 命令(cmd)

                例如：
                bilibili hot
                zhihu search

                不要输入：
                opencli bilibili hot
                cmd /c

                返回：
                该网站(site)的命令(cmd)的详细参数等帮助信息
            """),
            schema={
                "type": "object",
                "properties": {
                    "site": {"type": "string"},
                    "cmd": {"type": "string"},
                },
                "required": ["site", "cmd"],
            },
            fn=site_cmd_help,
        )

        # execute
        def opencli_execute(site_cmd, result_limit: int | None = None):
            def extract_limit(site_cmd):
                pattern = r"--limit\s*(?:=\s*|\s+)(\d+)"
                match = re.search(pattern, site_cmd)
                return int(match.group(1)) if match else None

            try:
                result_limit = int(result_limit) if result_limit is not None else None
            except (TypeError, ValueError):
                result_limit = None

            if result_limit is None:
                result_limit = extract_limit(site_cmd)

            for p in (
                "opencli ",
                "cmd ",
                "cmd /c ",
            ):
                if site_cmd.startswith(p):
                    site_cmd = site_cmd[len(p) :]
            # site_cmd = site_cmd.lower()
            r = self._execute_opencli_command(site_cmd, format_output="yaml")
            if not r.success:
                return r.error
            if r.data:
                result = r.to_dict()
                try:
                    data = result["data"]
                    if result_limit and isinstance(
                        data,
                        list,
                    ):
                        data = data[:result_limit]
                    elif (
                        result_limit
                        and isinstance(
                            data,
                            dict,
                        )
                        and isinstance(
                            data.get("items"),
                            list,
                        )
                    ):
                        data["items"] = data["items"][:result_limit]

                    if "toutiao" in site_cmd:
                        data = process_toutiao_data(data)
                    result["data"] = data

                except Exception as e:
                    print(f"处理 result_limit 时出错: {e}")
                    if self.verbose:
                        print(traceback.format_exc())

                # print(result["data"])
                return result["data"]

            return r.stdout

        self.register(
            name="opencli_execute",
            description=dedent("""\
                ## site_cmd
                执行某个完整命令字符串，大小写敏感                
                
                完整命令字符串的拼接格式:
                (site) (cmd) <command_options> --limit=条数
                
                比如:
                site_cmd = bilibili history --limit=10
                site_cmd = zhihu hot --limit=5
                site_cmd = 12306 trains --from=成都东 --to=北京西 --date=2026-06-05

                当需要控制返回结果条数, 且命令支持--limit 参数时:
                必须在添加 --limit 参数！
                
                不要输入：
                opencli
                cmd
                -f 格式
                系统会自动补充

                不要输入site_cmd字符串本身，比如错误的例子:
                site_cmd = site_cmd=bilibili history

                ## result_limit
                如果需要限制条数, 则必须传入 result_limit 参数, 可与 --limit 同时使用
                
                例如：
                result_limit = 10
            """),
            schema={
                "type": "object",
                "properties": {
                    "site_cmd": {"type": "string"},
                    "result_limit": {"type": "integer"},
                },
                "required": ["site_cmd"],
            },
            fn=opencli_execute,
        )

        # date
        def get_today_date():
            return date.today().strftime("%Y-%m-%d")

        self.register(
            name="get_today_date",
            description=dedent("""\
                获取当天日期

                返回：
                格式为 yyyy-mm-dd 的日期字符串，例如：2026-05-23
            """),
            schema={
                "type": "object",
                "properties": {},
            },
            fn=get_today_date,
        )

    # api
    def get_tools(self):
        return list(self._schemas.values())

    def execute(self, name, args):
        if name not in self._functions:
            raise Exception(f"未知工具:{name}")

        return self._functions[name](**args)
