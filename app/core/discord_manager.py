# app/core/discord_manager.py
"""
Manager para integrar Discord con el sistema principal
"""
import asyncio
import logging
from typing import Optional
from .agent import BotAgent

logger = logging.getLogger(__name__)


class DiscordManager:
    def __init__(self, agent: BotAgent):
        self.agent = agent
        self.discord_adapter: Optional = None
        self.bot_task: Optional[asyncio.Task] = None
        self._initialized = False

    async def initialize(self):
        """Inicializa el manager de Discord"""
        if self._initialized:
            return

        try:
            logger.info("🎮 Inicializando Discord...")

            # Importar y crear adaptador
            from ..adapters.discord import DiscordAdapter
            self.discord_adapter = DiscordAdapter(self.agent)

            if self.discord_adapter.is_enabled():
                # Iniciar bot en tarea separada (es bloqueante)
                self.bot_task = asyncio.create_task(self._run_bot())

                # Esperar un poco para verificar que se inició correctamente
                await asyncio.sleep(3)

                if self.discord_adapter.running:
                    logger.info("✅ Discord integrado y funcionando")
                else:
                    logger.error("❌ Discord falló al iniciar")
                    if self.bot_task:
                        self.bot_task.cancel()
                        self.bot_task = None
            else:
                logger.info("ℹ️ Discord no configurado (DISCORD_BOT_TOKEN faltante)")

            self._initialized = True

        except ImportError as e:
            logger.error(f"❌ Error importando DiscordAdapter: {e}")
            logger.error("💡 Verifica que existe app/adapters/discord.py")
        except Exception as e:
            logger.error(f"❌ Error inicializando Discord: {e}")

    async def _run_bot(self):
        """Ejecuta el bot de Discord en tarea separada"""
        try:
            await self.discord_adapter.start()
        except asyncio.CancelledError:
            logger.info("🔄 Tarea de Discord cancelada")
        except Exception as e:
            logger.error(f"❌ Error en tarea de Discord: {e}")
        finally:
            if self.discord_adapter:
                self.discord_adapter.running = False

    async def shutdown(self):
        """Cierra el manager de Discord"""
        logger.info("👋 Cerrando Discord...")

        # Cancelar tarea del bot
        if self.bot_task and not self.bot_task.done():
            self.bot_task.cancel()
            try:
                await self.bot_task
            except asyncio.CancelledError:
                pass
            self.bot_task = None

        # Cerrar adaptador
        if self.discord_adapter and self.discord_adapter.running:
            await self.discord_adapter.stop()

        logger.info("✅ Discord desconectado")

    def get_status(self):
        """Obtiene el estado de Discord"""
        if not self.discord_adapter:
            return {"status": "not_initialized"}

        status = {
            "status": "running" if self.discord_adapter.running else "stopped",
            "task_running": self.bot_task and not self.bot_task.done() if self.bot_task else False,
            **self.discord_adapter.get_status()
        }

        return status

    def get_adapter(self):
        """Obtiene el adaptador (para acceso directo si es necesario)"""
        return self.discord_adapter

    async def restart(self):
        """Reinicia el manager de Discord"""
        logger.info("🔄 Reiniciando Discord...")

        # Cerrar actual
        await self.shutdown()

        # Resetear estado
        self._initialized = False
        self.discord_adapter = None
        self.bot_task = None

        # Reinicializar
        await self.initialize()

        return self.get_status()

    async def send_test_message(self, channel_id: int, message: str = "Test desde MeshChile Bot"):
        """Envía un mensaje de prueba"""
        if not self.discord_adapter or not self.discord_adapter.running:
            return {"success": False, "error": "Discord no está corriendo"}

        return await self.discord_adapter.send_test_message(channel_id, message)