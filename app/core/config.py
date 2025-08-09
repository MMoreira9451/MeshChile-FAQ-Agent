# app/core/config.py
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Raztor/Mentha Configuration
    API_KEY: str  # Requerido desde .env
    BASE_URL: str = "https://llm.raztor.cl"  # Valor por defecto OK
    MODEL_NAME: str = "NVD.llama3.1:8b"  # Valor por defecto OK  
    COLLECTION_ID: str  # Requerido desde .env

    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_TITLE: str = "Bot Agent API"
    API_VERSION: str = "1.0.0"
    API_DEBUG: bool = False

    # Session Configuration
    SESSION_TTL: int = 3600  # 1 hora
    MAX_SESSION_MESSAGES: int = 20

    # Platform Tokens - WhatsApp Business API
    WHATSAPP_VERIFY_TOKEN: Optional[str] = None
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_PREFERRED_METHOD: str = "auto"  # "auto", "api", "web"

    # Platform Tokens - Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None

    # Platform Tokens - Discord
    DISCORD_BOT_TOKEN: Optional[str] = None
    DISCORD_APPLICATION_ID: Optional[str] = None
    DISCORD_GUILD_ID: Optional[int] = None
    DISCORD_CHANNEL_ID: Optional[int] = None

    # Model Configuration
    MODEL_TIMEOUT: int = 60
    MODEL_TEMPERATURE: float = 0.7

    # Logging
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True

    @property
    def redis_full_url(self) -> str:
        """Construye URL completa de Redis desde componentes"""
        if self.REDIS_URL and "redis://" in self.REDIS_URL:
            return self.REDIS_URL

        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


settings = Settings()