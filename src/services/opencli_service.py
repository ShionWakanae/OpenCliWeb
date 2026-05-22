# services/opencli_service.py

import time
import traceback
from utils.settings import settings
from llama_index.llms.openai_like import OpenAILike
from opencli.IntelligentAgent import IntelligentCLIAgent
from opencli.OpenCLITool import OpenCLITool


def create_agent(
    base_url="https://api.openai.com/v1",
    api_key="",
    model="gpt-4o-mini",
    system_prompt="",
    opencli_profile=None,
    verbose=False,
    on_execute=None,  # ←新增
):

    llm = OpenAILike(
        model=model,
        api_base=base_url,
        api_key=api_key,
        is_chat_model=True,
        is_function_calling_model=True,
        temperature=0,
        system_prompt=system_prompt,
    )

    opencli_tool = OpenCLITool(
        profile=opencli_profile,
        verbose=verbose,
        on_execute=on_execute,
    )

    return IntelligentCLIAgent(
        llm=llm,
        opencli_tool=opencli_tool,
        verbose=verbose,
    )


class OpenCLIService:
    def __init__(self):
        self.events = []

        def on_execute(event):
            self.events.append(event)

        self.agent = create_agent(
            base_url=settings.llm_api_base,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            verbose=False,
            on_execute=on_execute,
        )

    async def stream_answer(
        self,
        question,
    ):
        total_start = time.perf_counter()
        query_ms = time.perf_counter()
        yield {
            "type": "trace",
            "stage": "开始",
            "message": "收到用户指令并开始处理……",
            "timing": 0,
        }
        total_answer = 0
        try:
            full_answer = []
            got_answer = False
            first_token = False
            async for event in self.agent.astream(question):
                if event["type"] == "token":
                    text = event["text"]
                    if text:
                        got_answer = True
                        full_answer.append(text)

                    if not first_token:
                        first_token = True
                        query_ms = round(
                            (time.perf_counter() - total_start) * 1000,
                            2,
                        )
                        total_answer = time.perf_counter()
                yield event

            llm_ms = round(
                (time.perf_counter() - total_answer) * 1000,
                2,
            )
            total_ms = round(
                (time.perf_counter() - total_start) * 1000,
                2,
            )

            yield {
                "type": "debug",
                "query_ms": query_ms,
                "llm_ms": llm_ms,
                "total_ms": total_ms,
            }

            yield {
                "type": "status",
                "got_answer": got_answer,
                "source": "opencli",
            }

        except Exception as e:
            yield {
                "type": "token",
                "text": str(e),
            }

            yield {
                "type": "status",
                "got_answer": True,
                "source": "error",
            }
            print(traceback.format_exc())


service = OpenCLIService()
