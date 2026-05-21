import os
from dotenv import load_dotenv

version_num = "0.3.0"

class Settings:
    def __init__(self):
        load_dotenv()
        self.webui_username = os.getenv("WEBUI_USERNAME")
        self.webui_password = os.getenv("WEBUI_PASSWORD")
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "7860"))
        # LLM
        self.llm_api_base = self._required("LLM_API_BASE")
        self.llm_api_key = self._required("LLM_API_KEY")
        self.llm_model = self._required("LLM_MODEL")
        self.storage_secret = self._required("STORAGE_SECRET")  # you need this

    def _required(self, key: str):
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Missing required environment variable: {key}")

        return value

settings = Settings()
