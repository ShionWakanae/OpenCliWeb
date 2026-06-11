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
from collections import defaultdict
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


# def keep_fields(obj, fields_to_keep):
#     """递归只保留指定列表中的字段，删除其他字段"""
#     if isinstance(obj, dict):
#         fields_to_delete = [key for key in obj.keys() if key not in fields_to_keep]
#         for field in fields_to_delete:
#             del obj[field]
#         for key, value in obj.items():
#             obj[key] = keep_fields(value, fields_to_keep)
#     elif isinstance(obj, list):
#         for i, item in enumerate(obj):
#             obj[i] = keep_fields(item, fields_to_keep)
#     return obj


def reduce_site_help_field(data):
    if "commands" not in data:
        return data
    for item in data["commands"]:
        # remove empty positionals
        if (
            "positionals" in item
            and item["positionals"] is not None
            and len(item["positionals"]) == 0
        ):
            del item["positionals"]

        # shorten description
        if "description" in item:
            item["desc"] = item.pop("description")

        # shorten and remove empty command_options
        if "command_options" in item:
            item["options"] = item.pop("command_options")
            if item["options"] is not None and len(item["options"]) == 0:
                del item["options"]

        # use example if usage is shorter or missing
        if "usage" in item:
            example = item["usage"]
            if "example" in item:
                example = item["example"]
                if example.endswith(" -f yaml"):
                    example = example[:-8]
            if len(item["usage"]) < len(example):
                item["usage"] = example
        elif "example" in item:
            example = item["example"]
            if example.endswith(" -f yaml"):
                example = example[:-8]
            item["usage"] = example

        # if usage ends with [options] but there are no options, remove it.
        if "options" not in item and item["usage"].endswith(" [options]"):
            item["usage"] = item["usage"][:-10]

    # remove unnecessary fields
    fields = [
        "site",  # one site help
        "browser_common_options",  # do not send browser common options
        "common_options",  # do not send common options
        "next",  # no next command
        "columns",  # no need to know detail
        "example",  # is transfered to usage
        "command",  # dup with usage and example
        "access",  # no need to know detail
        "domain",  # no need to know detail
        "browser",  # no need to know detail
        "positional",  # all positionals are positional
        "required",  # all positionals are required
        "type",
    ]
    return remove_fields(data, fields)


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
        self.tools_called = defaultdict(int)
        self.tools_success = defaultdict(int)
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
        result_limit: int | None = None,
    ):
        format_output = format_output.lower()
        cmd = ["cmd", "/c", *self.base_args, *shlex.split(command)]
        if format_output and "-f" not in command and "--format" not in command:
            cmd.extend(["-f", format_output])

        full_cmd = " ".join(cmd)
        if self.tools_success[f"{full_cmd} {result_limit}"] >= 1:
            return CommandResult(
                success=False,
                command=full_cmd,
                stdout="",
                stderr="",
                data=None,
                error="ok: false\nerror: duplicated cmd execution attempt, please check the previous results.",
                data_format=format_output,
            )

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
                    command=full_cmd,
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

            self.tools_success[f"{full_cmd} {result_limit}"] += 1
            return CommandResult(
                success=True,
                command=full_cmd,
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
        r = self._execute_opencli_command(command="--help", format_output="yaml")
        if not r.success:
            log(r.error)
            raise Exception(r.error)
        if r.data:
            if "site_adapters" in r.data:
                if "sites" in r.data["site_adapters"]:
                    data = r.data["site_adapters"]["sites"]
                    # print(data)
                    return data
        print(r)
        raise Exception("获取网站列表失败!")

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
        def site_help(site):
            if site not in self._sites:
                return f"error: ({site}) is not a supported site name!"
            r = self._execute_opencli_command(f"{site} --help", format_output="yaml")
            if not r.success:
                return r.error
            if r.data:
                data = r.data
                data = reduce_site_help_field(data)
                # print(data)
                return data

            return r.stdout

        self.register(
            name="site_help",
            description=dedent("""\
                输入：
                网站名(site)

                返回：
                该网站(site)的全部命令(cmd)和参数
            """),
            schema={
                "type": "object",
                "properties": {"site": {"type": "string"}},
                "required": ["site"],
            },
            fn=site_help,
        )

        # execute
        def cmd_exec(full_cmd, result_limit: int | None = None):
            def extract_limit(full_cmd):
                pattern = r"--limit\s*(?:=\s*|\s+)(\d+)"
                match = re.search(pattern, full_cmd)
                return int(match.group(1)) if match else None

            try:
                result_limit = int(result_limit) if result_limit is not None else None
            except (TypeError, ValueError):
                result_limit = None

            if result_limit is None:
                result_limit = extract_limit(full_cmd)

            for p in (
                "opencli ",
                "cmd ",
                "cmd /c ",
            ):
                if full_cmd.startswith(p):
                    full_cmd = full_cmd[len(p) :]

            r = self._execute_opencli_command(
                full_cmd, format_output="yaml", result_limit=result_limit
            )
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

                    if "toutiao" in full_cmd:
                        data = process_toutiao_data(data)

                    # remove unnecessary fields
                    fields = [
                        "image_url",  # no need
                    ]
                    result["data"] = remove_fields(data, fields)

                except Exception as e:
                    print(f"处理 result_limit 时出错: {e}")
                    if self.verbose:
                        print(traceback.format_exc())

                # print(result["data"])
                return result["data"]

            return r.stdout

        self.register(
            name="cmd_exec",
            description=dedent("""\
                ## **full_cmd**
                待执行的完整命令字符串(大小写敏感)

                完整命令字符串的组成: 
                "网站名称 命令名称 positional参数1 positional参数2 ... --option参数1 值1 --option参数2 值2 ..."

                格式如下:
                site cmd positional(s) --option(s) option_value
                
                控制条数:
                需要控制返回条数时, 只要 options 中包含 limit参数 ，则必须添加 --limit

                不要输入：
                "full_cmd"字符串本身
                opencli
                cmd
                -f 格式
                系统会自动补充

                ## **result_limit**
                如需限制条数则必须传入 result_limit 参数, 可与 --limit 同时使用

                例如：
                result_limit = 5
            """),
            schema={
                "type": "object",
                "properties": {
                    "full_cmd": {"type": "string"},
                    "result_limit": {"type": "integer"},
                },
                "required": ["full_cmd"],
            },
            fn=cmd_exec,
        )

        # date
        def today_date():
            return date.today().strftime("%Y-%m-%d")

        self.register(
            name="today_date",
            description=dedent("""\
                获取当天日期

                返回：
                格式为 yyyy-mm-dd 的日期字符串
            """),
            schema={
                "type": "object",
                "properties": {},
            },
            fn=today_date,
        )

    # api
    def get_tools(self):
        return list(self._schemas.values())

    def execute(self, name, args):
        if name not in self._functions:
            raise Exception(f"未知工具:{name}")

        return self._functions[name](**args)
