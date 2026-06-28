import asyncio

# import json
import argparse
from rich import print
from utils.charstrings import display_width, truncate_by_width_approx
from services.opencli_service import service
from utils.logger import logger

log = logger.log


async def main(question, think=False, verbose=False):
    accumulated = ""
    accumulated_reasoning = ""
    got_answer = False
    first_token = False
    first_reasoning = False
    timing = {}
    model_name = ""
    prompt_tokens = 0
    completion_tokens = 0
    last_print_char = "\n"
    async for event in service.stream_answer(question, think=think, verbose=verbose):
        if event["type"] == "token":
            chunk = event["text"]
            if len(accumulated_reasoning) > 0:
                print(f"[dark_magenta]{accumulated_reasoning}[/]", end="", flush=True)
                last_print_char = accumulated_reasoning[-1]
                accumulated_reasoning = ""
            if not first_token:
                log(
                    "Streaming...",
                    need_newline_first=last_print_char != "\n",
                )
                first_token = True
            accumulated += chunk
            # 遇到换行，或超过某长度个字符时输出
            if "\n" in accumulated or len(accumulated) > 23:
                print(f"[bright_magenta]{accumulated}[/]", end="", flush=True)
                last_print_char = accumulated[-1]
                accumulated = ""

        elif event["type"] == "reasoning":
            if len(accumulated) > 0:
                print(f"[bright_magenta]{accumulated}[/]", end="", flush=True)
                last_print_char = accumulated[-1]
                accumulated = ""
            chunk = event["text"]
            if not first_reasoning:
                log(
                    "Reasoning...",
                    need_newline_first=last_print_char != "\n",
                )
                first_reasoning = True
            accumulated_reasoning += chunk
            if "\n" in accumulated_reasoning or len(accumulated_reasoning) > 23:
                print(
                    f"[dark_magenta]{accumulated_reasoning}[/]",
                    end="",
                    flush=True,
                )
                last_print_char = accumulated_reasoning[-1]
                accumulated_reasoning = ""

        elif event["type"] == "usage":
            if not model_name:
                model_name = event["model"]
            prompt_tokens += int(event["usage"]["prompt_tokens"])
            completion_tokens += int(event["usage"]["completion_tokens"])
            if len(accumulated) > 0:
                print(f"[bright_magenta]{accumulated}[/]", end="", flush=True)
                last_print_char = accumulated[-1]
                accumulated = ""
            if len(accumulated_reasoning) > 0:
                print(f"[dark_magenta]{accumulated_reasoning}[/]", end="", flush=True)
                last_print_char = accumulated_reasoning[-1]
                accumulated_reasoning = ""
        elif event["type"] == "trace":
            if len(accumulated) > 0:
                print(f"[bright_magenta]{accumulated}[/]", end="", flush=True)
                last_print_char = accumulated[-1]
                accumulated = ""
            if len(accumulated_reasoning) > 0:
                print(f"[dark_magenta]{accumulated_reasoning}[/]", end="", flush=True)
                last_print_char = accumulated_reasoning[-1]
                accumulated_reasoning = ""
            log(
                msg=f"[{event['stage']}] {event['message']}",
                need_newline_first=last_print_char != "\n",
            )
            last_print_char = "\n"

        elif event["type"] == "tool":
            tool_name = event.get("tool_name")
            kwargs = event.get("kwargs")
            stage = event.get("stage")
            text_content = event.get("text_content")
            text_len = event.get("text_len")
            if text_len > 0:
                # print(text_content)
                text_content = f"({text_len}) {text_content}"
            text_content = text_content.replace("\\n", "")
            text_content = " ".join(text_content.split())
            text_content_with_format = text_content
            if stage == "→" and kwargs:
                stage = f"{stage} {kwargs}"

            prefix = f"[工具] {tool_name} {stage}"
            if text_content:
                text_content_with_format = f" [bold bright_blue]{text_content}[/]"
                if stage != "→":
                    text_content_with_format = (
                        f"{truncate_by_width_approx(text_content_with_format, 140)}..."
                        if display_width(text_content_with_format) > 140
                        else f"{text_content_with_format}"
                    )
                    count = text_content_with_format.count("'")
                    if count % 2 == 1:
                        text_content_with_format += "'"
            log(
                msg=f"{prefix}{text_content_with_format}",
                need_newline_first=last_print_char != "\n",
            )
            last_print_char = "\n"

        # debug
        elif event["type"] == "debug":
            timing = event

        # status
        elif event["type"] == "status":
            got_answer = event["got_answer"]

    if accumulated:
        print(f"[bold bright_magenta]{accumulated}[/]", flush=True)
        print()

    streaming_s = round(timing.get("llm_ms", 0) / 1000, 2)
    print()
    if got_answer:
        log("Answer completed")
    else:
        log("No answer...")
    log(
        f"Retrieval: {timing.get('query_ms', 0)} ms, Answers: {timing.get('llm_ms', 0)} ms, Total: {timing.get('total_ms', 0)} ms",
        False,
    )
    tps = 0 if streaming_s == 0 else round(int(completion_tokens) / streaming_s, 2)
    log(
        f"Prompt Tokens: {prompt_tokens}, Completion Tokens: {completion_tokens}, <[bold bright_green]{model_name}[/]>"
        + f" <{tps} tokens/s>",
        False,
    )
    log("All done ✅")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "question",
        help="Question text",
    )
    parser.add_argument(
        "--Think",
        action="store_true",
        default=False,
        help="Enable thinking",
    )
    parser.add_argument(
        "--Verbose",
        action="store_true",
        default=False,
        help="Verbose output",
    )
    args = parser.parse_args()
    quest_str = args.question
    think = args.Think
    verbose = args.Verbose
    log(f"[Question] [bold bright_yellow]{quest_str}[/]", False)
    asyncio.run(main(quest_str, think, verbose))
