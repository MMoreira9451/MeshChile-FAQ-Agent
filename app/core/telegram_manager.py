# app/core/telegram_manager.py
"""
Manager para integrar Telegram con el sistema principal
"""
import asyncio
import logging
from typing import Optional
from .agent import BotAgent
from ..adapters.telegram import TelegramAdapter

logger = logging.getLogger(__name__)


class TelegramManager:
    def __init__(self, agent: BotAgent):
        self.agent = agent
        self.telegram_adapter: Optional[TelegramAdapter] = None
        self._initialized = False

    async def initialize(self):
        """Inicializa el manager de Telegram"""
        if self._initialized:
            return

        try:
            self.telegram_adapter = TelegramAdapter(self.agent)

            if self.telegram_adapter.is_enabled():
                await self.telegram_adapter.start_polling()
                logger.info("✅ Telegram integrado y funcionando")
            else:
                logger.info("ℹ️ Telegram no configurado (TELEGRAM_BOT_TOKEN faltante)")

            self._initialized = True

        except Exception as e:
            logger.error(f"❌ Error inicializando Telegram: {e}")

    async def shutdown(self):
        """Cierra el manager de Telegram"""
        if self.telegram_adapter and self.telegram_adapter.running:
            await self.telegram_adapter.stop_polling()
            logger.info("👋 Telegram desconectado")

    def get_status(self):
        """Obtiene el estado de Telegram"""
        if not self.telegram_adapter:
            return {"status": "not_initialized"}

        return {
            "status": "running" if self.telegram_adapter.running else "stopped",
            **self.telegram_adapter.get_status()
        }

    def get_adapter(self):
        """Obtiene el adaptador (para webhook si es necesario)"""
        return self.telegram_adapter