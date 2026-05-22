import asyncio
import argparse
from rich import print
from services.opencli_service import service
from utils.logger import logger

log = logger.log


async def main(question):
    accumulated = ""
    first = True
    async for event in service.stream_answer(question):
        if event["type"] == "token":
            chunk = event["text"]
            if first:
                log("Streaming...")
                first = False
            accumulated += chunk
            # 遇到句号、感叹号、问号或换行时输出
            if "\n" in accumulated or len(accumulated) > 23:
                print(f"[bold bright_magenta]{accumulated}[/]", end="", flush=True)
                accumulated = ""

        elif event["type"] == "trace":
            log(f"[{event['stage']}] {event['message']}")
        elif event["type"] == "tool":
            tool_name = event.get("tool_name")
            kwargs = event.get("kwargs")
            stage = f"{event.get('stage')}"
            if stage == "→" and kwargs:
                stage = f"{stage} {kwargs}"

            text_content = event.get("text_content")
            text_content_with_format = ""
            if tool_name == "opencli_list":
                text_content = ""
            if text_content:
                text_content = text_content.replace("\n", " ")[:50] + "..."
                text_content_with_format = f" [bold bright_blue]{text_content}[/]"
            msg_str = f"[工具] {tool_name} {stage}{text_content_with_format}"
            log(msg_str)

    if accumulated:
        print(f"[bold bright_magenta]{accumulated}[/]", flush=True)
        print()

    print()
    print()
    log("All done ✅")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "question",
        help="Question text",
    )
    args = parser.parse_args()
    quest_str = args.question
    log(f"Question: [bold bright_yellow]{quest_str}[/]", False)
    asyncio.run(main(quest_str))
