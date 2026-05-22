import subprocess
import json
import shlex
import traceback
import re
from datetime import date
from textwrap import dedent
from dataclasses import dataclass
from typing import Any
import asyncio


@dataclass
class CommandResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    data: Any = None
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

    # execute
    async def _execute_command_async(
        self,
        command,
        format_json=True,
    ):
        return await asyncio.to_thread(
            self._execute_command,
            command,
            format_json,
        )

    def _execute_command(
        self,
        command,
        format_json=True,
    ):

        cmd = [
            "cmd",
            "/c",
            *self.base_args,
            *shlex.split(command),
        ]

        if format_json and "-f" not in command and "--format" not in command:
            cmd.extend(
                [
                    "-f",
                    "json",
                ]
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
                print("[OpenCLI]", cmd)

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
            if format_json and result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                except Exception:
                    if self.verbose:
                        print(traceback.format_exc())

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

        # help
        def opencli_help(command):
            command = command.replace("_", " ")
            r = self._execute_command(
                f"{command} --help",
                format_json=False,
            )
            if r.success:
                return r.stdout

            return r.error

        self.register(
            name="opencli_help",
            description=dedent("""\
                查看某个网站支持哪些操作。

                输入：
                网站名

                例如：
                bilibili
                zhihu

                不要输入：
                opencli bilibili
                cmd /c

                返回：
                该网站支持的子命令列表。
            """),
            schema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            fn=opencli_help,
        )

        # execute
        def opencli_execute(subcommand, limit=None):
            try:
                limit = int(limit) if limit is not None else None
            except (TypeError, ValueError):
                limit = None

            for p in (
                "opencli ",
                "cmd ",
                "cmd /c ",
            ):
                if subcommand.startswith(p):
                    subcommand = subcommand[len(p) :]

            r = self._execute_command(
                subcommand,
                True,
            )
            result = r.to_dict()
            try:
                data = result["data"]
                if limit and isinstance(
                    data,
                    list,
                ):
                    result["data"] = data[:limit]
                elif (
                    limit
                    and isinstance(
                        data,
                        dict,
                    )
                    and isinstance(
                        data.get("items"),
                        list,
                    )
                ):
                    data["items"] = data["items"][:limit]

            except Exception as e:
                print(f"处理 limit 时出错: {e}")
                if self.verbose:
                    print(traceback.format_exc())
            return result

        self.register(
            name="opencli_execute",
            description=dedent("""\
                ## subcommand 参数
                执行某个网站命令
                格式:
                subcommand=<网站名> <命令>

                比如:
                subcommand=bilibili history
                subcommand=zhihu hot

                不要输入：
                opencli
                cmd
                -f
                json

                系统会自动补充。

                ## limit(整数) 参数，可选。限制返回结果的数量。
                例如：
                limit=10
            """),
            schema={
                "type": "object",
                "properties": {
                    "subcommand": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["subcommand"],
            },
            fn=opencli_execute,
        )

        # list
        def opencli_list():
            r = self._execute_command("list", False)
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
            name="opencli_list",
            description=dedent("""\
                仅列出支持的网站。
                不要用来查看具体命令。
                查看命令请调用 opencli_help。
            """),
            schema={
                "type": "object",
                "properties": {},
            },
            fn=opencli_list,
        )

        # date
        def get_today_date():
            return date.today().strftime("%Y-%m-%d")

        self.register(
            name="get_today_date",
            description=dedent("""\
                获取当天日期。

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
