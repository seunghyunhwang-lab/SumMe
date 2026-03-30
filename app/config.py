from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent.parent / ".env"
load_dotenv(_ENV_FILE, override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8")

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # 서버
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # 파이프라인 보안 키 (스케줄러 → API 호출 시 사용)
    pipeline_secret: str = "dev-secret"


settings = Settings()
