import asyncio
import datetime
from pathlib import Path
import traceback
import markdown
from nicegui import ui
from nicegui import app
from nicegui import context
from rich import print
import re
from services.opencli_service import service
from utils.logger import logger
from utils.settings import (
    settings,
    version_num,
)

log = logger.log


def get_speed_str(total_ms: float) -> str:
    if total_ms < 500:
        speed_str = "⚡"
    elif total_ms < 2000:
        speed_str = "🚀"
    elif total_ms < 5000:
        speed_str = "✈️"
    elif total_ms < 10000:
        speed_str = "🚅"
    elif total_ms < 20000:
        speed_str = "🚗"
    elif total_ms < 40000:
        speed_str = "🏃"
    elif total_ms < 60000:
        speed_str = "🚶"
    else:
        speed_str = "🐢"
    return speed_str


def auth_guard():
    if not app.storage.user.get("authenticated", False):
        ui.navigate.to("/login")


def logout():
    app.storage.user.clear()
    ui.navigate.to("/login")


app.add_static_files("/static/js", "./src/ui/js")
app.add_static_files("/static/css", "./src/ui/css")
app.add_static_files("/static/images", "./res")


def render_markdown_html(md_str: str, class_name: str = "final-markdown") -> str:
    rendered_html = markdown.markdown(
        md_str,
        extensions=[
            "fenced_code",
            "tables",
            "nl2br",
            "extra",
            "sane_lists",
            "pymdownx.mark",
        ],
    )
    return f"""
            <div class="{class_name}">
                {rendered_html}
            </div>"""


def read_file_by_path(path):
    if not path:
        return "文件不存在！"

    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    except Exception as e:
        return f"读取失败:\n\n{e}"


def build_highlighted_markdown(content, hits):
    CODE_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
    lines = content.splitlines()
    first_hit_done = False
    # merge intervals
    normalized_hits = []
    for start, end in sorted(hits):
        if end <= start:
            continue

        if not normalized_hits:
            normalized_hits.append([start, end])
            continue

        _, last_end = normalized_hits[-1]
        if start <= last_end:
            normalized_hits[-1][1] = max(
                last_end,
                end,
            )
        else:
            normalized_hits.append([start, end])

    # highlighted line set
    highlighted = set()
    for start, end in normalized_hits:
        for i in range(start, end):
            highlighted.add(i)

    # rebuild markdown
    output = []

    # code fence state
    in_code_block = False
    current_fence = None

    for idx, line in enumerate(lines):
        # detect fence
        fence_match = CODE_FENCE_RE.match(line)
        if fence_match:
            fence = fence_match.group(1)
            # entering code block
            if not in_code_block:
                in_code_block = True
                current_fence = fence

            # leaving code block
            elif fence.startswith(current_fence[0]):
                in_code_block = False
                current_fence = None

            output.append(line)
            continue

        # do not highlight inside code block
        if in_code_block:
            output.append(line)
            continue

        # normal highlight logic
        if idx in highlighted:
            # avoid empty line highlight issue
            if line.strip() and not line.lstrip().startswith("#"):
                # markdown table
                if line.lstrip().startswith("|"):
                    parts = line.split("|")
                    # preserve original structure
                    is_separator = False
                    if len(parts) > 2:
                        non_empty_cells = [p for p in parts if p.strip()]
                        is_separator = all(
                            all(ch in "- :" for ch in cell.strip())
                            and "-" in cell.strip()
                            for cell in non_empty_cells
                            if cell.strip()
                        )

                    # separator row
                    if is_separator:
                        # 分隔行，保持原样
                        output.append(line)
                    # data row
                    else:
                        # 数据行，高亮每个单元格内容
                        result_parts = ["|"]  # 开头
                        for cell in parts[1:-1]:
                            stripped = cell.strip()
                            if stripped:
                                if not first_hit_done:
                                    result_parts.append(
                                        f' <mark id="first-hit">{stripped}</mark> |'
                                    )
                                    first_hit_done = True
                                else:
                                    result_parts.append(f" <mark>{stripped}</mark> |")
                            else:
                                result_parts.append(" |")
                        # 不需要额外加尾部的 |
                        marked_line = "".join(result_parts)
                        output.append(marked_line)
                # markdown list
                else:
                    # 检查当前行是否为列表项
                    m = re.match(r"^(\s*(?:\*|-|\+|\d+[.)])\s+)(.*)", line)
                    if m:
                        # 检查上一行是否为列表项
                        prev_line = output[-1] if output else ""
                        prev_is_list = re.match(
                            r"^\s*(?:\*|-|\+|\d+[.)])\s+",
                            prev_line,
                        )
                        if prev_line.strip() and not prev_is_list:
                            output.append("")

                        # 判断是否为第一个高亮项
                        if not first_hit_done:
                            output.append(
                                f"{m.group(1)}=={m.group(2)}==<mark id='first-hit'/>"
                            )
                            first_hit_done = True
                        else:
                            output.append(f"{m.group(1)}=={m.group(2)}==")
                    else:
                        if not first_hit_done:
                            output.append(f'=={line}== <mark id="first-hit"/>')
                            first_hit_done = True
                        else:
                            output.append(f"=={line}==")
            else:
                output.append(line)

        # normal line
        else:
            output.append(line)

    return "\n".join(output)


def auto_scroll_chat(client):
    client.run_javascript("scrollToBottom()")


@ui.page("/")
def main():
    auth_guard()
    chat_history = app.storage.user.setdefault("chat_history", [])

    def clear_chat():
        chat_history.clear()
        chat_scroll.clear()
        clear_menu_item.disable()
        clear_menu_item.style("filter: grayscale(1);")
        clear_badge.set_text("0")
        clear_badge.set_background_color("gray")
        switch_debug.set_value(False)
        switch_debug.set_enabled(False)
        debug_panel.content = """
        <div class="debug-panel">
            waiting for data...
        </div>
        """
        debug_panel.update()

    def confirm_clear():
        with ui.dialog().props("persistent") as dialog:
            with ui.card().style(
                """
                width: 500px;
                max-width: 90vw;
                background: #313131;
                """
            ):
                ui.markdown("### 清空聊天记录")
                ui.label("确定清空聊天记录吗，目前清空后聊天记录就无法恢复了哦？")

                with ui.row().classes("w-full justify-end gap-2 mt-4"):
                    ui.button("取消", on_click=dialog.close).props("flat icon='close'")
                    ui.button(
                        "确定",
                        on_click=lambda: (
                            clear_chat(),
                            dialog.close(),
                        ),
                    ).props("color=primary icon='check'")
        dialog.open()

    def show_inline_rag_confirm(question, container, client):
        container.clear()
        with container:
            ui.label("❓需要继续从资料库检索吗？").classes("text-sm text-gray-400")

            def on_yes():
                container.clear()
                container.delete()
                asyncio.create_task(
                    send_message(
                        question,
                        client=client,
                    )
                )

            def on_no():
                container.clear()
                container.delete()

            ui.button("否", on_click=on_no).props("flat dense size=sm icon='close'")
            ui.button("是", on_click=on_yes).props("dense size=sm icon='check'")

    def show_inline_force_rag_confirm(question, container, client):
        container.clear()
        with container:
            ui.label(f"❓需要重新强制检索'{question}'吗？？").classes(
                "text-sm text-gray-400"
            )

            def on_yes():
                container.clear()
                container.delete()
                asyncio.create_task(
                    send_message(
                        f"'{question}'",
                        client=client,
                    )
                )

            def on_no():
                container.clear()
                container.delete()

            ui.button("否", on_click=on_no).props("flat dense size=sm icon='close'")
            ui.button("是", on_click=on_yes).props("dense size=sm icon='check'")

    message_id = 0
    # page
    ui.add_head_html("""
        <script>
        window.MathJax = {
        tex: {
            inlineMath: [['$', '$'], ['\\\\(', '\\\\)']]
        }
        };
        </script>
        <style>
        </style>
        """)
    ui.add_head_html("""
        <link rel="stylesheet" href="/static/css/app.css">
    """)
    ui.add_body_html("""
        <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    """)
    ui.add_body_html("""
        <script src="/static/js/chat_scroll.js"></script>
    """)

    ui.dark_mode(True)
    ui.colors(
        primary="#4f8cff",
        secondary="#2d2d2d",
        accent="#1f1f1f",
        dark="#111111",
    )

    def show_hide_debug_panel(show: bool):
        if show:
            right_column.style("display: block;")
            outer_container.style(remove="max-width: 960px;")
            outer_container.style("max-width: 1280px;")
        else:
            outer_container.style(remove="max-width: 1280px;")
            outer_container.style("max-width: 960px;")
            right_column.style("display: none;")

    with ui.column().classes(
        "w-full h-screen max-w-7xl mx-auto px-0 sm:px-2 py-1 gap-0 overflow-hidden"
    ):
        with ui.row().classes("w-full items-center justify-between mt-0 mb-0"):
            # =========================
            # 左侧整体区域，logo，标题，快捷提问
            # =========================
            with ui.row().classes("""
                items-center
                flex-1
                min-w-0
                no-wrap
                overflow-hidden
            """):
                # logo区域（固定宽度）
                with (
                    ui.row()
                    .classes("""
                        items-center
                        gap-0
                        mt-0
                        mb-0
                        ml-4
                        flex-shrink-0
                    """)
                    .style("width: 100px;")
                ):
                    ui.icon("tips_and_updates").props("size=medium")
                    ui.label("我的小助手").style("font-size: 16px; font-weight: 600;")

                # 快捷问题区域（桌面显示）
                with ui.row().classes("""
                    gt-sm
                    items-center
                    gap-4
                    ml-4
                    mr-4
                    no-wrap
                    overflow-x-auto
                    flex-1
                    min-w-0
                """):
                    quick_questions = [
                        "目前B站上最热门的5条视频是？",
                        "我的B站的观看历史。",
                        "我的B站的收藏夹。",
                        "我的B站的动态详情。",
                        "我的小红书的通知。",
                        "小红书上关于PIU的视频。",
                        "抖音的官方活动列表",
                    ]

                    for q in quick_questions:
                        ui.button(q, on_click=lambda msg=q: send_message(msg)).props(
                            "flat dense size=sm"
                        )
                    switch_debug = ui.switch(
                        "debug", on_change=lambda e: show_hide_debug_panel(e.value)
                    )
                    switch_debug.set_enabled(False)

            # =========================
            # 右侧固定区域，版本号，菜单。
            # =========================
            with ui.row().classes("""
                items-center
                gap-2
                flex-shrink-0

                mr-2
            """):
                ui.label(f"ver {version_num}").style("""
                    font-size: 12px;
                    color: #888;
                """)

                with ui.button(icon="more_vert").props("flat round"):
                    clear_badge = ui.badge("0", color="gray").props("floating")
                    with ui.menu():
                        clear_menu_item = ui.menu_item(
                            "🧹 清空会话",
                            on_click=confirm_clear,
                        )
                        ui.separator()
                        ui.menu_item(
                            "🚪 退出登录",
                            on_click=logout,
                        )

        outer_container = (
            ui.row()
            .classes("w-full no-wrap outer-container")
            .style(
                """
                height: calc(100vh - 70px);
                max-width: 960px;
                margin: 0 auto;
                padding: 0px;
                gap: 0px;
                overflow: hidden;
                transition: height 0.3s ease;
                background: #313131;
                """
            )
        )
        with outer_container:
            # left
            left_column = ui.column().style(
                """
                position: relative;
                flex: 1;
                height: 100%;
                overflow: hidden;
                """
            )
            with left_column:
                (
                    ui.button(
                        icon="keyboard_arrow_down",
                        on_click=lambda: context.client.run_javascript(
                            "scrollToBottom()"
                        ),
                    )
                    .classes("scroll-to-bottom-btn")
                    .props("round")
                    .style("""
                        position: absolute;
                        bottom: 30px;
                        left: 50%;
                        transform: translateX(-50%);
                        z-index: 100;
                        opacity: 0.0;
                        transition: opacity 0.5s;
                    """)
                )

                # 空状态区域
                empty_state = (
                    ui.column()
                    .classes("empty-state items-center justify-center")
                    .style("""
                        position: absolute;
                        inset: 0;
                        z-index: 5;
                        pointer-events: none;
                        gap: 10px;
                        opacity: 1;
                        transition: opacity 0.25s ease;
                        transform: translateY(80px);
                    """)
                )

                with empty_state:
                    ui.image("/static/images/logo.png").style(
                        "width: 128px; height: 128px; opacity: 0.9;"
                    )

                    ui.label("我的小助手").style(
                        "font-size: 28px; font-weight: 700; color: #f0f0f0; letter-spacing: 1px; margin-top: 4px;"
                    )

                    ui.label(
                        "通过OpenCLI查询 Bilibili、微博、小红书、抖音等平台的内容"
                    ).style("""
                        white-space: pre-line;
                        text-align: center;
                        line-height: 1.7;
                        font-size: 15px;
                        color: #9aa4b2;
                        max-width: 520px;
                    """)

                # chat area
                chat_scroll = (
                    ui.column()
                    .classes("w-full chat-area")
                    .style(
                        """
                        flex: 1;
                        overflow-y: auto;
                        background: #303030;
                        border: none;
                        border-radius: 8px;
                        padding: 12px;
                        margin: 0px;
                        """
                    )
                )
                with chat_scroll:
                    for item in chat_history:
                        if not item["confirm"]:
                            with ui.row().classes("w-full justify-end"):
                                with ui.chat_message(
                                    sent=True,
                                    name="用户🧑",
                                    stamp=item["qtime"],
                                ).style("max-width: 85%;"):
                                    ui.markdown(item["question"])

                        with ui.column().classes("w-full items-start mt-0 mb-0"):
                            with ui.chat_message(
                                sent=False,
                                name="🧠历史回复",
                            ).style("max-width: 95%;"):
                                message_id += 1
                                ui.html(item["answer"]).props(
                                    f"id=assistant-msg{message_id}"
                                ).style("width: 100%;")
                                context.client.run_javascript(f"""
                                if (window.MathJax) {{
                                    MathJax.typesetPromise();
                                    const el = document.getElementById("assistant-msg{message_id}");
                                    MathJax.typesetPromise([el]);
                                }}
                                """)
                            if item["sources"]:
                                with (
                                    ui.row()
                                    .classes("gap-2 mt-0 mb-0")
                                    .style("max-width: 95%;")
                                ):
                                    for source in item["sources"]:
                                        with ui.row().classes("items-start gap-0"):
                                            ui.link(
                                                f"""
                                                📄{Path(source["file_name"]).stem}
                                                """,
                                                target=None,
                                            ).style(
                                                "cursor: pointer; text-decoration: none;"
                                            )

                alen = len(chat_scroll.default_slot.children)
                clear_badge.set_text(f"{alen}")
                if alen == 0:
                    clear_badge.set_background_color("gray")
                    clear_menu_item.disable()
                    clear_menu_item.style("filter: grayscale(100%);")

                else:
                    clear_badge.set_background_color("red")
                    clear_menu_item.enable()
                    clear_menu_item.style("filter: none;")

            # right
            right_column = ui.column().style(
                """
                width: 24%;
                height: 100%;
                overflow: hidden;
                display: none;
            """
            )

            with right_column:
                # debug
                debug_panel = ui.html(
                    """
                    <div class="debug-panel">
                        暂无调试信息
                    </div>
                    """
                ).classes("w-full")

                debug_panel.style(
                    """
                    width: 100%;
                    border: 1px solid #3a3a3a;
                    border-radius: 8px;
                    padding: 8px;
                    height: 100%;
                    overflow-y: auto;
                    font-size: 12px;
                    background: #1b1b1b;
                    """
                )
        # input row
        with (
            ui.row()
            .classes("w-full justify-center no-wrap")
            .style("padding-top: 4px; padding-bottom: 28px;")
        ):
            with (
                ui.input(placeholder="请输入简短关键字或完整问题...")
                .classes("chat-input")
                .props("clearable type=text inputmode=text enterkeyhint=send")
                .style("""
                    width: 100%;
                    max-width: 860px;
                    margin-left: 20px;
                    margin-right: 20px;
                """) as input_box
            ):
                with input_box.add_slot("append"):
                    send_button = ui.button(
                        icon="send",
                    ).props("flat round dense")

            async def send_message(
                message=None,
                client=None,
            ):
                partial_text = ""
                try:
                    if client is None:
                        client = context.client

                    if message is None:
                        message = (input_box.value or "").strip()

                    if not message:
                        return

                    input_box.value = ""
                    send_button.disable()
                    send_button.props("loading")
                    clear_menu_item.disable()
                    clear_menu_item.style("filter: grayscale(1);")
                    clear_badge.set_text(f"{len(chat_scroll.default_slot.children)}")
                    clear_badge.set_background_color("gray")

                    input_box.disable()
                    switch_debug.set_value(False)
                    switch_debug.set_enabled(False)
                    print("=" * 60)
                    log(f"Question: {message}", False)
                    # reset status
                    debug_panel.content = """
                    <div class="debug-panel">
                        waiting for data...
                    </div>
                    """
                    debug_panel.update()
                    # messages
                    qtime = f"🕐{datetime.datetime.now().strftime('%H:%M:%S')}"
                    with chat_scroll:
                        # 用户消息：右边
                        with ui.row().classes("w-full justify-end"):
                            with ui.chat_message(
                                sent=True,
                                name="用户🧑",
                                stamp=qtime,
                            ).style("max-width: 85%;"):
                                ui.markdown(message)

                        # 助理消息
                        with ui.column().classes("w-full items-start mt-0 mb-0"):
                            llm_msg = ui.chat_message(
                                sent=False,
                                name="✨智能助理",
                            ).style("max-width: 95%;")

                            with llm_msg:
                                with ui.column().classes(
                                    "w-full items-start mt-0 mb-0"
                                ):
                                    assistant_stage_spinner = ui.spinner(
                                        "dots", size="md"
                                    ).classes("mt-0 mb-0")
                                    assistant_answer_spinner = ui.spinner(
                                        "facebook", size="md"
                                    ).classes("mt-0 mb-0")
                                    assistant_answer_spinner.set_visibility(False)

                                    rendered_html = render_markdown_html("### 思考中")
                                    nonlocal message_id
                                    message_id += 1
                                    assistant_message = (
                                        ui.html(rendered_html)
                                        .props(f"id=assistant-msg{message_id}")
                                        .style(
                                            """
                                            width: 100%;
                                            """
                                        )
                                    )
                                    auto_scroll_chat(client)

                    # state
                    got_answer = False
                    first_token = False
                    first_trace = False
                    timing = {}
                    # consume
                    accumulated = ""
                    async for event in service.stream_answer(message):
                        if event is None:
                            break

                        # token
                        if event["type"] == "token":
                            got_answer = True
                            if not first_token:
                                log("Streaming...")
                                partial_text = ""
                                first_token = True
                                if assistant_stage_spinner:
                                    assistant_stage_spinner.set_visibility(False)
                                if assistant_answer_spinner:
                                    assistant_answer_spinner.set_visibility(True)
                            accumulated += event["text"]
                            if "\n" in accumulated:
                                partial_text += accumulated
                                accumulated = ""
                                rendered_html = render_markdown_html(partial_text)
                                assistant_message.content = rendered_html
                                assistant_message.update()
                                auto_scroll_chat(client)

                        elif event["type"] == "trace":
                            if not first_trace:
                                partial_text = "### 思考中\n\n"
                                first_trace = True
                            trace_stage = event["stage"]
                            trace_message = event["message"]
                            trace_timing = event["timing"]
                            msg_str = f"- **[{trace_stage}]** {trace_message}"
                            timing_str = (
                                "" if not trace_timing else f"(_{trace_timing}ms_)"
                            )
                            log(msg_str)
                            partial_text += f"{msg_str} {timing_str}\n\n"
                            rendered_html = render_markdown_html(partial_text)
                            assistant_message.content = rendered_html
                            assistant_message.update()
                            auto_scroll_chat(client)

                        # sources
                        elif event["type"] == "tool":
                            kwargs = event.get("kwargs")
                            msg = f"({event['stage']})"
                            if kwargs:
                                msg += f" {kwargs}"
                            text_content = event["text_content"]
                            if text_content:
                                text_content = (
                                    '"'
                                    + event["text_content"].replace("\n", " ")[:50]
                                    + '"...'
                                )
                            msg_str = f"- **[工具]** {event['tool_name']} {msg} {text_content}"
                            log(msg_str)
                            partial_text += msg_str + "\n"
                            rendered_html = render_markdown_html(partial_text)
                            assistant_message.content = rendered_html
                            assistant_message.update()
                            auto_scroll_chat(client)

                        # debug
                        elif event["type"] == "debug":
                            timing = event
                            debug_panel.update()
                            switch_debug.set_enabled(True)

                        # status
                        elif event["type"] == "status":
                            got_answer = event["got_answer"]

                    if accumulated:
                        partial_text += accumulated
                    log("Answer completed")
                    log("----------------")
                    log(
                        f"Retrieval: {timing.get('query_ms', 0)} ms, Answers: {timing.get('llm_ms', 0)} ms, Total: {timing.get('total_ms', 0)} ms",
                        False,
                    )
                    print()

                    # fallback
                    if not got_answer:
                        partial_text = "对不起，我检索了资料，但还是不知道答案……"

                    atime = f"🕐{datetime.datetime.now().strftime('%H:%M:%S')}"
                    total_ms = timing.get("total_ms", 0)
                    speed_str = get_speed_str(float(total_ms))
                    footer = f"""
                        <br>
                        <div style="text-align:right; font-size:12px; color:#888888 !important;">
                        {speed_str}{logger.format_duration(total_ms)} &nbsp;&nbsp;&nbsp;&nbsp; {atime}
                        </div>
                    """
                    rendered_html = render_markdown_html(partial_text)
                    assistant_message.content = rendered_html + footer
                    assistant_message.update()
                    client.run_javascript(f"""
                    if (window.MathJax) {{
                        MathJax.typesetPromise();
                        const el = document.getElementById("assistant-msg{message_id}");
                        MathJax.typesetPromise([el]);
                    }}
                    """)

                    history_item = {
                        "question": message,
                        "qtime": qtime,
                        "answer": rendered_html + footer,
                        "atime": atime,
                        "confirm": False,
                        "sources": [],
                    }
                    chat_history.append(history_item)

                except Exception as e:
                    partial_text += f"  \n  \n  `📛出现了错误：{str(e)}`！"
                    atime = f"🕐{datetime.datetime.now().strftime('%H:%M:%S')}"
                    rendered_html = render_markdown_html(partial_text)
                    log(e)
                    print(traceback.format_exc())
                    if assistant_message:
                        assistant_message.content = rendered_html
                        assistant_message.update()
                finally:
                    if assistant_stage_spinner:
                        assistant_stage_spinner.delete()
                    if assistant_answer_spinner:
                        assistant_answer_spinner.delete()
                    auto_scroll_chat(client)
                    send_button.enable()
                    send_button.props(remove="loading")
                    clear_menu_item.enable()
                    clear_menu_item.style("filter: none;")
                    clear_badge.set_text(f"{len(chat_scroll.default_slot.children)}")
                    clear_badge.set_background_color("red")
                    input_box.enable()

            # enter submit
            input_box.on(
                "keydown.enter",
                lambda e: send_message(),
            )
            send_button.on("click", send_message)


@ui.page("/login")
def login():
    ui.add_head_html("""
        <link rel="stylesheet" href="/static/css/app.css">
    """)
    if app.storage.user.get("authenticated", False):
        ui.navigate.to("/")
        return

    def try_login():
        if (
            username.value == settings.webui_username
            and password.value == settings.webui_password
        ):
            app.storage.user["authenticated"] = True
            ui.navigate.to("/")
        else:
            ui.notify("用户名或密码错误", color="negative", position="center")

    with (
        ui.column()
        .classes("absolute-center items-center w-80 gap-4")
        .style("""
        transform: translate(-50%, -30%);
    """)
    ):
        ui.image("/static/images/logo.png").style(
            "width: 128px; height: 128px; opacity: 0.9;"
        )
        ui.label("我的小助手").style("font-size:28px; font-weight:700;")

        username = (
            ui.input(placeholder="请输入用户名")
            .classes("chat-input w-full")
            .props("clearable")
        )
        password = (
            ui.input(
                placeholder="请输入密码",
                password=True,
                password_toggle_button=True,
            )
            .classes("chat-input w-full")
            .props("clearable")
        )
        password.on(
            "keydown.enter",
            lambda e: try_login(),
        )

        with password.add_slot("append"):
            ui.button(
                icon="login",
                on_click=try_login,
            ).props("flat round dense")


# run app
ui.run(
    host=settings.host,
    port=settings.port,
    title="我的小助手",
    language="zh-CN",
    storage_secret=settings.storage_secret,
    reload=False,
    dark=True,
)
