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
                print(
                    f"[bold bright_magenta]{accumulated}[/]", end="", flush=True
                )
                accumulated = ""

        elif event["type"] == "trace":
            log(f"[{event['stage']}] {event['message']}")
        elif event["type"] == "tool":
            kwargs = event.get("kwargs")
            msg = f"({event['stage']})"
            if kwargs:
                msg += f" {kwargs}"
            log(f"[工具] {event['message']} {msg}")

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
