import json
from textwrap import dedent
from openai import AsyncOpenAI
from utils.settings import settings


class SiteAgent:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_api_base,
        )

        self.model = settings.llm_model

    def _get_system_prompt(self):
        return dedent(
            """
            请根据网站支持的commands信息，
            用一句中文概括该网站用途。

            要求：
            1. 不超过10个字
            2. 不允许猜测不存在的功能
            3. 不允许输出解释
            4. 返回JSON

            格式：

            {
              "desc": "B站视频平台"
            }
            """
        )

    async def generate_site_description(
        self,
        site: str,
        help_data,
    ) -> str:

        messages = [
            {
                "role": "system",
                "content": self._get_system_prompt(),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "site": site,
                        "help": help_data,
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
            stream=False,
            extra_body={
                "chat_template_kwargs": {"enable_thinking": False},
                "enable_thinking": False,
                "thinking": {"type": "disabled"},
            },
        )

        content = response.choices[0].message.content

        try:
            result = json.loads(content)
            return result.get("desc", "").strip()

        except Exception:
            return ""
