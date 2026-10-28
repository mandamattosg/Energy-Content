import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Energy Radar"
    environment: str = "development"
    timezone: str = "America/Sao_Paulo"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/energy_radar"
    data_retention_days: int = 90

    @property
    def sqlalchemy_database_url(self) -> str:
        # Railway entrega "postgresql://" (ou "postgres://"); o SQLAlchemy precisa do driver psycopg explicito.
        url = self.database_url
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model_name: str = Field(default="gemini-3.8-flash", alias="GEMINI_MODEL_NAME")
    # minimal | low | medium | high; vazio = padrao do modelo.
    gemini_thinking_level: str = Field(default="low", alias="GEMINI_THINKING_LEVEL")
    telegram_token: str = Field(default="", alias="TELEGRAM_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    lookback_days: int = 7
    collector_retry_attempts: int = 3
    collector_retry_delay_seconds: float = 1.5
    collector_timeout_seconds: float = 15.0
    reddit_user_agent: str = "Mozilla/5.0 EnergyRadar/0.1"

    # Payload menor = resposta mais rapida do LLM (60 sinais x 500 chars gerava 504 DEADLINE_EXCEEDED).
    analysis_max_total_signals: int = 40
    analysis_max_official_signals: int = 14
    analysis_max_news_signals: int = 22
    analysis_max_reddit_signals: int = 5
    analysis_max_trends_signals: int = 8
    analysis_max_content_length: int = 350
    near_duplicate_threshold: float = 0.85

    model_config = SettingsConfigDict(
        # Os testes definem ENERGY_RADAR_ENV_FILE="" para nunca carregar o .env real.
        env_file=os.environ.get("ENERGY_RADAR_ENV_FILE", ".env") or None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
