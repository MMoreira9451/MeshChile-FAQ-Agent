# app/adapters/discord.py
import httpx
from typing import Dict
from ..core.agent import BotAgent
from ..core.config import settings


class DiscordAdapter:
    def __init__(self, agent: BotAgent):
        self.agent = agent
        self.bot_token = settings.DISCORD_BOT_TOKEN

    async def handle_interaction(self, request: Dict):
        """Maneja interacciones de Discord"""

        interaction_type = request.get("type")

        # Ping (verification)
        if interaction_type == 1:
            return {"type": 1}

        # Slash command
        if interaction_type == 2:
            return await self._handle_slash_command(request)

        return {"type": 4, "data": {"content": "Tipo de interacción no soportado"}}

    async def _handle_slash_command(self, interaction: Dict):
        """Maneja comandos slash de Discord"""

        data = interaction.get("data", {})
        command_name = data.get("name")
        user = interaction.get("member", {}).get("user", {})
        user_id = user.get("id")
        guild_id = interaction.get("guild_id")

        if command_name == "chat":
            options = data.get("options", [])
            message = ""

            for option in options:
                if option.get("name") == "message":
                    message = option.get("value", "")
                    break

            if not message:
                return {
                    "type": 4,
                    "data": {"content": "❌ Por favor proporciona un mensaje"}
                }

            # Procesar con el agente
            session_id = f"discord_{guild_id}_{user_id}"

            try:
                response = await self.agent.process_message(
                    message=message,
                    session_id=session_id,
                    platform="discord",
                    user_id=str(user_id)
                )

                return {
                    "type": 4,
                    "data": {"content": response}
                }
            except Exception as e:
                return {
                    "type": 4,
                    "data": {"content": f"❌ Error procesando mensaje: {str(e)}"}
                }

        return {
            "type": 4,
            "data": {"content": f"❌ Comando '{command_name}' no reconocido"}
        }