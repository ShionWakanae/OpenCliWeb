import asyncio
import argparse
from rich import print
from services.opencli_service import service
from utils.logger import logger

log = logger.log


async def main(question, verbose=False):
    accumulated = ""
    got_answer = False
    first_token = False
    timing = {}
    model_name = ""
    prompt_tokens = 0
    completion_tokens = 0
    async for event in service.stream_answer(question, verbose=verbose):
        if event["type"] == "token":
            chunk = event["text"]
            if first_token:
                log("Streaming...")
                first_token = False
            accumulated += chunk
            # 遇到句号、感叹号、问号或换行时输出
            if "\n" in accumulated or len(accumulated) > 23:
                print(f"[bold bright_magenta]{accumulated}[/]", end="", flush=True)
                accumulated = ""

        elif event["type"] == "usage":
            if not model_name:
                model_name = event["model"]
            prompt_tokens += int(event["usage"]["prompt_tokens"])
            completion_tokens += int(event["usage"]["completion_tokens"])

        elif event["type"] == "trace":
            log(f"[{event['stage']}] {event['message']}")

        elif event["type"] == "tool":
            tool_name = event.get("tool_name")
            kwargs = event.get("kwargs")
            stage = event.get("stage")
            text_content = event.get("text_content")
            text_content = text_content.replace("\n", " ").replace("\\n", " ")
            text_content_with_format = text_content
            if stage == "→" and kwargs:
                stage = f"{stage} {kwargs}"
            if stage != "→" and tool_name == "opencli_list":
                text_content = f"{len(text_content.split())} sites"
                text_content_with_format = text_content

            prefix = f"[工具] {tool_name} {stage}"
            if text_content:
                text_content = (
                    f"`{text_content[:60]}...`"
                    if len(text_content) > 60
                    else f"`{text_content}`"
                )
                text_content_with_format = f" [bold bright_blue]{text_content}[/]"
            log(f"{prefix}{text_content_with_format}")

        # debug
        elif event["type"] == "debug":
            timing = event

        # status
        elif event["type"] == "status":
            got_answer = event["got_answer"]

    if accumulated:
        print(f"[bold bright_magenta]{accumulated}[/]", flush=True)
        print()

    if got_answer:
        log("Answer completed")
    else:
        log("No answer...")
    log(
        f"Retrieval: {timing.get('query_ms', 0)} ms, Answers: {timing.get('llm_ms', 0)} ms, Total: {timing.get('total_ms', 0)} ms",
        False,
    )
    log(
        f"Prompt Tokens: {prompt_tokens}, Completion Tokens: {completion_tokens} <[bold bright_green]{model_name}[/]>",
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
        "--Verbose",
        action="store_true",
        default=False,
        help="Verbose output",
    )
    args = parser.parse_args()
    quest_str = args.question
    verbose = args.Verbose
    log(f"Question: [bold bright_yellow]{quest_str}[/]", False)
    asyncio.run(main(quest_str, verbose))
