import datetime
from pathlib import Path
import traceback
import markdown
from nicegui import ui, app, context, background_tasks
from rich import print
import time
from services.opencli_service import service
from utils.logger import logger
from utils.settings import settings, version_num
from utils.charstrings import display_width, truncate_by_width_approx


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
                    ui.space()
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
                        "我能查看哪些网站(sites)",
                        "B站若苗瞬的文章",
                        "B站若苗瞬的动态时间线",
                        "今日头条5条热门",
                        "携程上米易县的景点",
                        "Arxiv上Ivan Perov的论文",
                        "devto的最新文章",
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
                                    stamp=item.get("qtime", ""),
                                ).style("max-width: 85%;"):
                                    ui.markdown(item.get("question", ""))

                        with ui.column().classes("w-full items-start mt-0 mb-0"):
                            with ui.chat_message(
                                sent=False,
                                name="🧠历史回复",
                            ).style("max-width: 95%;"):
                                with ui.column().classes(
                                    "w-full items-start mt-0 mb-0"
                                ):
                                    message_id += 1
                                    # "trace": trace_message_ui.content,
                                    with ui.expansion("执行过程").style(
                                        "width: 100%; max-width: 100%; overflow-x: auto;"
                                    ):
                                        ui.html(item.get("trace", "")).style(
                                            "width: 100%;"
                                        )
                                    ui.html(item.get("answer", "")).props(
                                        f"id=assistant-msg{message_id}"
                                    ).style("width: 100%;")
                                    context.client.run_javascript(f"""
                                    if (window.MathJax) {{
                                        MathJax.typesetPromise();
                                        const el = document.getElementById("assistant-msg{message_id}");
                                        MathJax.typesetPromise([el]);
                                    }}
                                    """)

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

            @background_tasks.await_on_shutdown
            async def send_message(
                message=None,
                client=None,
            ):
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
                    log(f"[Question] [bold bright_yellow]{message}[/]", False)
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
                                    trace_expansion = ui.expansion("执行中……").style(
                                        "width: 100%; max-width: 100%; overflow-x: auto;"
                                    )
                                    trace_expansion.open()
                                    with trace_expansion:
                                        trace_message_ui = ui.html().style(
                                            "width: 100%;"
                                        )
                                    nonlocal message_id
                                    message_id += 1
                                    assistant_message = (
                                        ui.html("")
                                        .props(f"id=assistant-msg{message_id}")
                                        .style("width: 100%;")
                                    )
                                    auto_scroll_chat(client)

                    # state
                    got_answer = False
                    timing = {}
                    # consume
                    accumulated = ""
                    accumulated_reasoning = ""
                    model_name = ""
                    prompt_tokens = 0
                    completion_tokens = 0
                    trace_message_content = ""
                    assistant_message_content = ""

                    first_token = False
                    first_reasoning = False
                    streaming_start = time.perf_counter()
                    async for event in service.stream_answer(message):
                        if event is None:
                            break

                        # token
                        if event["type"] == "token":
                            if not first_token:
                                log("Streaming...")
                                first_token = True
                                streaming_start = time.perf_counter()
                            if (
                                assistant_stage_spinner
                                and assistant_stage_spinner.visible
                            ):
                                assistant_stage_spinner.set_visibility(False)
                            if (
                                assistant_answer_spinner
                                and not assistant_answer_spinner.visible
                            ):
                                assistant_answer_spinner.set_visibility(True)
                            accumulated += event["text"]
                            # still need a len limit, for a very long answer without newline
                            if "\n" in accumulated or len(accumulated) > 150:
                                assistant_message_content += accumulated
                                accumulated = ""
                                assistant_message.content = render_markdown_html(
                                    assistant_message_content
                                )
                                assistant_message.update()
                                auto_scroll_chat(client)

                        elif event["type"] == "reasoning":
                            if not first_reasoning:
                                log("Reasoning...")
                                first_reasoning = True
                            accumulated_reasoning += event["text"]
                            if (
                                "\n" in accumulated_reasoning
                                or len(accumulated_reasoning) > 150
                            ):
                                trace_message_content += accumulated_reasoning
                                accumulated_reasoning = ""
                                trace_message_ui.content = render_markdown_html(
                                    trace_message_content
                                )
                                trace_message_ui.update()
                                auto_scroll_chat(client)

                        elif event["type"] == "usage":
                            if not model_name:
                                model_name = event["model"]
                            prompt_tokens += int(event["usage"]["prompt_tokens"])
                            completion_tokens += int(
                                event["usage"]["completion_tokens"]
                            )

                        elif event["type"] == "trace":
                            trace_stage = event["stage"]
                            trace_message = event["message"]
                            trace_timing = event["timing"]
                            msg_str = f"- **[{trace_stage}]** {trace_message}"
                            timing_str = (
                                "" if not trace_timing else f"(_{trace_timing}ms_)"
                            )
                            log(msg_str)
                            if (
                                len(trace_message_content) > 0
                                and trace_message_content[-1] != "\n"
                            ):
                                trace_message_content += "\n"
                            trace_message_content += f"{msg_str} {timing_str}\n"
                            assistant_message.content = ""
                            trace_message_ui.content = render_markdown_html(
                                trace_message_content
                            )
                            assistant_message.update()
                            trace_message_ui.update()
                            auto_scroll_chat(client)

                        elif event["type"] == "tool":
                            streaming_start = time.perf_counter()
                            if (
                                assistant_stage_spinner
                                and not assistant_stage_spinner.visible
                            ):
                                assistant_stage_spinner.set_visibility(True)
                            if (
                                assistant_answer_spinner
                                and assistant_answer_spinner.visible
                            ):
                                assistant_answer_spinner.set_visibility(False)
                            trace_message_content += assistant_message_content + (
                                accumulated + "\n\n" if accumulated else ""
                            )
                            assistant_message_content = ""
                            accumulated = ""
                            tool_name = event.get("tool_name")
                            kwargs = event.get("kwargs")
                            stage = event.get("stage")
                            text_content = event.get("text_content")
                            text_content = text_content.replace("\n", " ").replace(
                                "\\n", " "
                            )

                            if stage == "→" and kwargs:
                                stage = f"{stage} {kwargs}"

                            text_content_with_format = text_content
                            prefix = f"- **[工具]** {tool_name} {stage}"
                            if text_content:
                                text_content_with_format = (
                                    f" [bold bright_blue]{text_content}[/]"
                                )
                                text_content = (
                                    f" `{truncate_by_width_approx(text_content, 50)}...`"
                                    if display_width(text_content) > 50
                                    else f" `{text_content}`"
                                )
                                if stage != "→":
                                    text_content_with_format = (
                                        f"{truncate_by_width_approx(text_content_with_format, 140)}..."
                                        if display_width(text_content_with_format) > 140
                                        else f"{text_content_with_format}"
                                    )

                            log(f"{prefix}{text_content_with_format}")
                            if (
                                len(trace_message_content) > 0
                                and trace_message_content[-1] != "\n"
                            ):
                                trace_message_content += "\n"
                            trace_message_content += f"{prefix}{text_content}" + "\n"
                            assistant_message.content = ""
                            trace_message_ui.content = render_markdown_html(
                                trace_message_content
                            )
                            assistant_message.update()
                            trace_message_ui.update()
                            auto_scroll_chat(client)

                        # debug
                        elif event["type"] == "debug":
                            timing = event
                            debug_panel.update()
                            switch_debug.set_enabled(False)

                        # status
                        elif event["type"] == "status":
                            got_answer = event["got_answer"]

                    if accumulated:
                        assistant_message_content += accumulated
                    if assistant_answer_spinner:
                        assistant_answer_spinner.set_visibility(False)
                    if assistant_stage_spinner:
                        assistant_stage_spinner.set_visibility(False)
                    trace_code_end = (
                        "```" if trace_message_content[-1] == "\n" else "\n```"
                    )
                    trace_message_ui.content = render_markdown_html(
                        f"```markdown\n{trace_message_content}{trace_code_end}"
                    )
                    trace_expansion.text = "执行过程"
                    trace_expansion.close()
                    trace_message_ui.update()
                    auto_scroll_chat(client)

                    streaming_s = round(
                        (time.perf_counter() - streaming_start),
                        2,
                    )
                    log("Answer completed")
                    log("----------------")
                    log(
                        f"Retrieval: {timing.get('query_ms', 0)} ms, Answers: {timing.get('llm_ms', 0)} ms, Total: {timing.get('total_ms', 0)} ms",
                        False,
                    )
                    tps = (
                        0
                        if streaming_s == 0
                        else round(int(completion_tokens) / streaming_s, 2)
                    )
                    log(
                        f"Prompt Tokens: {prompt_tokens}, Completion Tokens: {completion_tokens} <[bold bright_green]{model_name}[/]>"
                        + f" <{tps} tokens/s>",
                        False,
                    )
                    print()

                    # fallback
                    if not got_answer:
                        assistant_message_content += (
                            "\n对不起，我不知道哪里出了问题，无法完成你的要求……"
                        )

                    atime = f"🕐{datetime.datetime.now().strftime('%H:%M:%S')}"
                    total_ms = timing.get("total_ms", 0)
                    speed_str = get_speed_str(float(total_ms))
                    if model_name:
                        source_hint = f"🌐{model_name}"
                    else:
                        source_hint = ""
                    footer = f"""
                        <br>
                        <div style="text-align:right; font-size:12px; color:#888888 !important;">
                        {source_hint}&nbsp;&nbsp;&nbsp;&nbsp;{speed_str}{logger.format_duration(total_ms)}&nbsp;&nbsp;&nbsp;{atime}
                        </div>
                    """
                    assistant_message.content = (
                        render_markdown_html(assistant_message_content) + footer
                    )
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
                        "trace": trace_message_ui.content,
                        "answer": assistant_message.content,
                        "atime": atime,
                        "confirm": False,
                    }
                    chat_history.append(history_item)

                except Exception as e:
                    log(e)
                    print(traceback.format_exc())
                    assistant_message_content += f"  \n  \n  `📛出现了错误：{str(e)}`！"
                    atime = f"🕐{datetime.datetime.now().strftime('%H:%M:%S')}"
                    if assistant_message:
                        assistant_message.content = render_markdown_html(
                            assistant_message_content
                        )
                        assistant_message.update()
                finally:
                    if assistant_stage_spinner:
                        assistant_stage_spinner.set_visibility(False)
                        assistant_stage_spinner.update()
                    if assistant_answer_spinner:
                        assistant_answer_spinner.set_visibility(False)
                        assistant_answer_spinner.update()
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


async def cleanup():
    print("准备关闭应用...")


app.on_shutdown(cleanup)

# run app
try:
    ui.run(
        host=settings.host,
        port=settings.port,
        title="我的小助手",
        language="zh-CN",
        storage_secret=settings.storage_secret,
        reload=False,
        dark=True,
    )
except KeyboardInterrupt:
    print("应用程序已关闭.")
