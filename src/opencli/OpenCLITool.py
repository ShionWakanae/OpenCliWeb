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

        # list
        def opencli_sites_list():
            r = self._execute_opencli_command("list")
            if not r.success:
                return r.error

            sites = []
            for line in r.stdout.splitlines():
                if re.match(
                    r"^  \S+\s*$",
                    line,
                ):
                    sites.append(line.strip())

            return "\n".join(sites)

        self.register(
            name="opencli_sites_list",
            description=dedent("""\
                仅列出支持的网站
                不要用来查看具体命令
                查看命令请调用 opencli_site_help
            """),
            schema={
                "type": "object",
                "properties": {},
            },
            fn=opencli_sites_list,
        )

        # help
        def opencli_site_help(site):
            site = site.replace("_", " ").lower()
            r = self._execute_opencli_command(f"{site} --help", format_output="yaml")
            if not r.success:
                return r.error
            if r.data:
                data = r.data
                fields = [
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
            name="opencli_site_help",
            description=dedent("""\
                查看某个网站支持哪些操作，网站名称大小写敏感

                输入：
                网站名(site)

                例如：
                bilibili
                zhihu

                不要输入：
                opencli bilibili
                cmd /c

                返回：
                该网站支持的子命令列表
                包括子命令是否支持'limit'选项(command_options)
            """),
            schema={
                "type": "object",
                "properties": {"site": {"type": "string"}},
                "required": ["site"],
            },
            fn=opencli_site_help,
        )

        # execute
        def opencli_execute(site_cmd, result_limit: int | None = None):
            try:
                result_limit = int(result_limit) if result_limit is not None else None
            except (TypeError, ValueError):
                result_limit = None

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
                执行某个网站命令，网站名称和命令大小写敏感                
                
                网站命令的格式:
                (site) (command)
                
                或:
                (site) (command) --limit=(条数)    
                
                说明: 如果site_cmd支持可选的 <limit> 选项，且用户表达了对返回条数的需求
                使用 --limit 可增加或减少实际返回的结果数量

                比如:
                site_cmd = bilibili history
                site_cmd = zhihu hot --limit=5

                不要输入：
                opencli
                cmd
                -f 格式
                系统会自动补充

                不要输入site_cmd字符串本身，比如错误的例子:
                site_cmd = site_cmd=bilibili history

                ## result_limit
                后期限制(仅减少)返回结果的数量
                只要需要限制条数, 则必须传入 result_limit 参数, 以防止 --limit 失效的情况
                
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
