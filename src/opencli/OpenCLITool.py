# opencli_tool.py
import subprocess
import json
import shlex
from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass
import traceback
import re
from textwrap import dedent
from llama_index.core.tools import FunctionTool


@dataclass
class CommandResult:
    """命令执行结果"""

    success: bool
    stdout: str = ""
    stderr: str = ""
    data: Any = None  # 解析后的 JSON 数据
    command: str = ""
    error: str = ""

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "data": self.data if self.data else self.stdout,
            "error": self.error,
            "command": self.command,
        }


class OpenCLITool:
    """把 opencli 命令封装成可调用的工具函数"""

    def __init__(
        self,
        profile: Optional[str] = None,
        verbose: bool = False,
        timeout: int = 90,
        on_execute=None,
    ):
        self.on_execute = on_execute
        self.profile = profile
        self.verbose = verbose
        self.timeout = timeout
        self.base_args = ["opencli"]

        if profile:
            self.base_args.extend(["--profile", profile])

        # 工具注册表
        self._function_tools = {}
        self._register_all_tools()

    def _execute_command(self, command: str, format_json: bool = True) -> CommandResult:
        """执行 opencli 命令"""
        cmd = [
            "cmd",
            "/c",
            *self.base_args,
            *shlex.split(command),
        ]

        # 默认添加 json 格式
        if format_json and "-f" not in command and "--format" not in command:
            cmd.extend(["-f", "json"])

        if self.on_execute:
            self.on_execute(
                {
                    "type": "tool",
                    "stage": "execute",
                    "command": command,
                }
            )
        try:
            if self.verbose:
                print(f"[OpenCLI] 执行: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                encoding="utf-8",
            )
            if self.on_execute:
                self.on_execute(
                    {
                        "type": "tool",
                        "stage": "finished",
                        "command": command,
                        "success": result.returncode == 0,
                    }
                )
            if self.verbose:
                print(result)
            if result.returncode != 0:
                return CommandResult(
                    success=False,
                    stderr=result.stderr,
                    command=" ".join(cmd),
                    error=f"Exit code {result.returncode}: {result.stderr}",
                )

            # 尝试解析 JSON
            data = None
            if format_json and result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                except json.JSONDecodeError as e:
                    print(f"JSON解析失败: {e}")
                    print(result.stdout[:1000])
                    if self.verbose:
                        print(traceback.format_exc())

            return CommandResult(
                success=True,
                stdout=result.stdout,
                stderr=result.stderr,
                data=data,
                command=" ".join(cmd),
            )

        except subprocess.TimeoutExpired:
            return CommandResult(
                success=False,
                error=f"命令执行超时 ({self.timeout}秒)",
                command=" ".join(cmd),
            )
        except Exception as e:
            if self.verbose:
                print(traceback.format_exc())
            return CommandResult(success=False, error=str(e), command=" ".join(cmd))

    def _create_function_tool(
        self, name: str, description: str, fn: Callable
    ) -> FunctionTool:
        """创建 FunctionTool"""
        return FunctionTool.from_defaults(fn=fn, name=name, description=description)

    def _register_all_tools(self):
        """注册所有 opencli 工具"""

        # 1. 获取帮助信息
        def get_help(command: str) -> str:
            """获取 opencli 命令的帮助信息"""
            command = command.replace("_", " ")
            result = self._execute_command(f"{command} --help", format_json=False)
            if result.success:
                return result.stdout
            return f"无法获取帮助: {result.error}"

        self._function_tools["opencli_help"] = self._create_function_tool(
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
            fn=get_help,
        )

        # 2. 执行任意命令
        def execute_command(subcommand: str, limit: int | None = None) -> Dict:
            """执行 opencli 子命令"""

            try:
                limit = int(limit) if limit is not None else None
            except (TypeError, ValueError):
                limit = None

            prefixes = (
                "opencli ",
                "cmd ",
                "cmd /c ",
            )
            for p in prefixes:
                if subcommand.startswith(p):
                    subcommand = subcommand[len(p) :]
            result = self._execute_command(
                f"{subcommand} --window background", format_json=True
            )
            try:
                # 后处理 limit
                if limit and result.success and result.data is not None:
                    # 数组
                    if isinstance(result.data, list):
                        result.data = result.data[:limit]
                    # {"items":[...]}
                    elif isinstance(result.data, dict) and isinstance(
                        result.data.get("items"),
                        list,
                    ):
                        result.data["items"] = result.data["items"][:limit]
            except Exception as e:
                print(f"后处理 limit 时出错: {e}")
                if self.verbose:
                    print(traceback.format_exc())

            return result.to_dict()

        self._function_tools["opencli_execute"] = self._create_function_tool(
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
            fn=execute_command,
        )

        # 11. 列出所有可用命令
        def list_commands():
            result = self._execute_command("list", format_json=False)
            if not result.success:
                return result.error

            sites = []
            for line in result.stdout.splitlines():
                # 只保留一级命令
                if re.match(r"^  \S+\s*$", line):
                    sites.append(line.strip())

            return "\n".join(sites)

        self._function_tools["opencli_list"] = self._create_function_tool(
            name="opencli_list",
            description=dedent("""\
                仅列出支持的网站。
                不要用来查看具体命令。
                查看命令请调用 opencli_help。
            """),
            fn=list_commands,
        )

    def get_all_tools(self) -> List[FunctionTool]:
        """获取所有注册的工具"""
        return list(self._function_tools.values())

    def get_tool_by_name(self, name: str) -> Optional[FunctionTool]:
        """根据名称获取工具"""
        return self._function_tools.get(name)
