# app/adapters/telegram.py
import httpx
import asyncio
import sys
import os
from typing import Dict, Optional, List
import logging
import re

logger = logging.getLogger(__name__)


class TelegramAdapter:
    def __init__(self, agent):
        self.agent = agent
        self.bot_token = None
        self.base_url = None
        self.bot_username = None  # Para detectar menciones
        self.bot_id = None  # Para detectar respuestas a mensajes del bot
        self.offset = 0
        self.running = False
        self.polling_task = None

        # Importar configuración de forma segura
        try:
            from app.core.config import settings
            self.bot_token = settings.TELEGRAM_BOT_TOKEN
            if self.bot_token:
                self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        except ImportError:
            try:
                from ..core.config import settings
                self.bot_token = settings.TELEGRAM_BOT_TOKEN
                if self.bot_token:
                    self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
            except ImportError:
                logger.error("❌ No se pudo importar configuración")

    async def _get_bot_info(self):
        """Obtiene información del bot (especialmente el username e ID)"""
        if not self.base_url:
            return False

        try:
            url = f"{self.base_url}/getMe"
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)

                if response.status_code == 200:
                    result = response.json()
                    if result.get("ok"):
                        bot_info = result.get("result", {})
                        self.bot_username = bot_info.get("username", "")
                        self.bot_id = bot_info.get("id")  # ¡IMPORTANTE para detectar respuestas!
                        logger.info(f"✅ Bot: {bot_info.get('first_name')} (@{self.bot_username}) ID: {self.bot_id}")
                        return True

        except Exception as e:
            logger.error(f"Error obteniendo info del bot: {e}")

        return False

    def _is_bot_mentioned(self, text: str, entities: List[Dict] = None, reply_to_message: Dict = None) -> bool:
        """Verifica si el bot fue mencionado o si es respuesta a un mensaje del bot"""
        if not text or not self.bot_username:
            return False

        # Método 1: Respuesta a un mensaje del bot
        if reply_to_message:
            reply_from = reply_to_message.get("from", {})
            reply_from_id = reply_from.get("id")
            reply_from_username = reply_from.get("username", "")

            # Si responde a un mensaje del bot
            if reply_from_id == self.bot_id or reply_from_username == self.bot_username:
                logger.info(f"💬 Detectada respuesta al bot")
                return True

        # Método 2: Mención directa @username
        mention_pattern = f"@{self.bot_username}"
        if mention_pattern.lower() in text.lower():
            logger.info(f"🏷️ Detectada mención por @username")
            return True

        # Método 3: Revisar entities de tipo "mention"
        if entities:
            for entity in entities:
                if entity.get("type") == "mention":
                    offset = entity.get("offset", 0)
                    length = entity.get("length", 0)
                    mention_text = text[offset:offset + length]
                    if mention_text.lower() == mention_pattern.lower():
                        logger.info(f"🏷️ Detectada mención por entity")
                        return True

        return False

    def _clean_mention_from_text(self, text: str) -> str:
        """Limpia las menciones del texto para procesamiento"""
        if not self.bot_username:
            return text

        # Remover @username del texto
        mention_pattern = f"@{self.bot_username}"
        cleaned_text = re.sub(
            re.escape(mention_pattern),
            "",
            text,
            flags=re.IGNORECASE
        ).strip()

        return cleaned_text

    def _get_session_id(self, chat_id: int, user_id: int, chat_type: str) -> str:
        """Genera session ID apropiado según el tipo de chat"""
        if chat_type == "private":
            # Chat privado: sesión individual
            return f"telegram_private_{chat_id}_{user_id}"
        else:
            # Grupo/supergrupo: sesión por grupo (compartida)
            return f"telegram_group_{chat_id}"

    async def handle_webhook(self, request: Dict):
        """Maneja webhooks de Telegram (para compatibilidad)"""
        message = request.get("message")
        if not message:
            return {"status": "no_message"}

        await self._process_message(message)
        return {"status": "ok"}

    async def _process_message(self, message: Dict):
        """Procesa un mensaje individual con soporte para grupos"""
        try:
            # Extraer información del mensaje
            chat = message.get("chat", {})
            chat_id = chat.get("id")
            chat_type = chat.get("type", "private")  # private, group, supergroup, channel
            chat_title = chat.get("title", "")

            user = message.get("from", {})
            user_id = user.get("id")
            user_name = user.get("first_name", "Usuario")
            username = user.get("username", "")

            text = message.get("text", "")
            entities = message.get("entities", [])
            reply_to_message = message.get("reply_to_message")  # ¡NUEVO!

            if not chat_id or not user_id:
                return

            # Log del mensaje
            chat_info = f"({chat_type})" if chat_type == "private" else f"({chat_type}: {chat_title})"
            logger.info(f"📨 Telegram {chat_info} - {user_name}: {text[:50]}...")

            # Lógica diferente según tipo de chat
            if chat_type == "private":
                # Chat privado: procesar normalmente
                await self._handle_private_message(message, chat_id, user_id, user_name, text)

            elif chat_type in ["group", "supergroup"]:
                # Grupo: solo responder si está mencionado O si responden al bot
                await self._handle_group_message(message, chat_id, user_id, user_name, text, entities, chat_title,
                                                 reply_to_message)

            else:
                # Channels u otros: ignorar
                logger.info(f"ℹ️ Ignorando mensaje de tipo: {chat_type}")
                return

        except Exception as e:
            logger.error(f"❌ Error procesando mensaje de Telegram: {e}")

            # Respuesta de error amigable
            if 'chat_id' in locals():
                error_response = "Disculpa, tuve un problema procesando tu mensaje. ¿Puedes intentar de nuevo?"
                await self._send_message(chat_id, error_response)

    async def _handle_private_message(self, message: Dict, chat_id: int, user_id: int, user_name: str, text: str):
        """Maneja mensajes en chat privado"""

        # Comandos especiales
        if text == "/start":
            welcome = f"¡Hola {user_name}! 👋\n\n🔗 Soy el asistente FAQ de la comunidad **MeshChile Meshtastic**.\n\nPuedes preguntarme sobre:\n• Configuración de nodos\n• Integraciones disponibles\n• Funciones de la comunidad\n• Soporte técnico\n\nSolo escríbeme tu pregunta normalmente, sin comandos."
            await self._send_message(chat_id, welcome)
            return

        if text == "/help":
            help_text = "💡 **Bot FAQ MeshChile Meshtastic**\n\n**Temas que puedo ayudarte:**\n• 📡 Configuración de nodos Meshtastic\n• 🔧 Integraciones con la comunidad\n• 🗺️ Mapas y cobertura\n• 👥 Funciones de la red\n• 🆘 Soporte técnico\n\n**En grupos:** Mencioname con @bot pregunta\n**Chat privado:** Solo escribe tu pregunta"
            await self._send_message(chat_id, help_text)
            return

        # Ignorar otros comandos
        if text.startswith('/'):
            await self._send_message(chat_id,
                                     "No necesitas comandos. Solo pregúntame sobre Meshtastic o la comunidad MeshChile 😊")
            return

        # Manejar mensajes no texto
        if not text:
            await self._send_message(chat_id, "¿Tienes alguna pregunta sobre Meshtastic o la comunidad MeshChile?")
            return

        # Procesar con el agente
        await self._process_with_agent(chat_id, user_id, user_name, text, "private")

    async def _handle_group_message(self, message: Dict, chat_id: int, user_id: int, user_name: str, text: str,
                                    entities: List[Dict], chat_title: str, reply_to_message: Dict = None):
        """Maneja mensajes en grupos"""

        # Verificar si el bot fue mencionado O si es respuesta al bot
        if not self._is_bot_mentioned(text, entities, reply_to_message):
            # No mencionado y no es respuesta = no responder (evitar spam)
            return

        # Determinar el tipo de interacción
        interaction_type = "mención"
        if reply_to_message:
            reply_from = reply_to_message.get("from", {})
            if reply_from.get("id") == self.bot_id:
                interaction_type = "respuesta"

        logger.info(f"🏷️ Bot activado por {interaction_type} en grupo '{chat_title}' por {user_name}")

        # Limpiar menciones del texto para procesamiento
        clean_text = self._clean_mention_from_text(text).strip()

        # Comandos especiales en grupos
        if clean_text.lower() in ["/start", "start", "hola", "ayuda", "help"]:
            welcome = f"¡Hola {user_name}! 👋\n\n🔗 Soy el bot FAQ de **MeshChile Meshtastic**.\n\n📱 **En grupos**:\n• Mencioname: @{self.bot_username} tu pregunta\n• O responde a mis mensajes\n\n💬 **Chat privado**: Escríbeme directo\n\n🤖 Pregúntame sobre configuración, integraciones, cobertura, etc."
            await self._send_message(chat_id, welcome)
            return

        if not clean_text:
            await self._send_message(chat_id, f"{user_name}, ¿en qué puedo ayudarte con Meshtastic? 🔗")
            return

        # Procesar pregunta en grupo
        await self._process_with_agent(chat_id, user_id, user_name, clean_text, "group", chat_title)

    async def _process_with_agent(self, chat_id: int, user_id: int, user_name: str, text: str, chat_type: str,
                                  chat_title: str = None):
        """Procesa el mensaje con el agente"""
        try:
            # Mostrar que está escribiendo
            await self._send_typing_action(chat_id)

            # Generar session ID apropiado
            session_id = self._get_session_id(chat_id, user_id, chat_type)

            # Contexto adicional para el prompt
            context_info = f"Usuario: {user_name}"
            if chat_type == "group" and chat_title:
                context_info += f" (en grupo: {chat_title})"

            # Procesar con el agente
            response = await self.agent.process_message(
                message=text,
                session_id=session_id,
                platform=f"telegram_{chat_type}",
                user_id=str(user_id)
            )

            # En grupos, mencionar al usuario en la respuesta
            if chat_type == "group":
                response = f"{user_name}, {response}"

            # Enviar respuesta
            await self._send_message(chat_id, response)
            logger.info(f"✅ Respuesta enviada a {user_name} en {chat_type}")

        except Exception as e:
            logger.error(f"❌ Error procesando con agente: {e}")
            error_response = "Disculpa, tuve un problema procesando tu pregunta sobre Meshtastic. ¿Puedes intentar de nuevo?"

            if chat_type == "group":
                error_response = f"{user_name}, {error_response}"

            await self._send_message(chat_id, error_response)

    async def _send_message(self, chat_id: int, text: str, parse_mode: str = "Markdown"):
        """Envía un mensaje a Telegram"""
        if not self.base_url:
            logger.error("❌ No se puede enviar mensaje: bot_token no configurado")
            return False

        url = f"{self.base_url}/sendMessage"

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)

                if response.status_code == 200:
                    return True
                else:
                    logger.error(f"Error enviando mensaje Telegram: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Error de conexión enviando mensaje Telegram: {e}")
            return False

    async def _send_typing_action(self, chat_id: int):
        """Envía acción de 'escribiendo'"""
        if not self.base_url:
            return

        url = f"{self.base_url}/sendChatAction"

        payload = {
            "chat_id": chat_id,
            "action": "typing"
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json=payload)
        except:
            pass  # No es crítico si falla

    async def _get_updates(self, timeout=30):
        """Obtiene nuevos mensajes de Telegram (polling)"""
        if not self.bot_token or not self.base_url:
            return []

        url = f"{self.base_url}/getUpdates"

        params = {
            "offset": self.offset,
            "timeout": timeout,
            "allowed_updates": ["message"]
        }

        try:
            async with httpx.AsyncClient(timeout=timeout + 5) as client:
                response = await client.get(url, params=params)

                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        return data.get("result", [])
                    else:
                        logger.error(f"Error API Telegram: {data}")
                        return []
                else:
                    logger.error(f"Error HTTP Telegram: {response.status_code}")
                    return []

        except asyncio.TimeoutError:
            # Timeout es normal en long polling
            return []
        except Exception as e:
            logger.error(f"Error obteniendo updates: {e}")
            return []

    async def _polling_loop(self):
        """Loop principal de polling"""
        logger.info("🤖 Iniciando polling de Telegram...")

        # Obtener info del bot (especialmente username)
        if not await self._get_bot_info():
            logger.error("❌ No se pudo obtener información del bot")
            return

        while self.running:
            try:
                # Obtener nuevos mensajes
                updates = await self._get_updates()

                for update in updates:
                    # Actualizar offset
                    self.offset = update.get("update_id", 0) + 1

                    # Procesar mensaje
                    message = update.get("message")
                    if message:
                        await self._process_message(message)

                # Pequeña pausa si no hay mensajes
                if not updates:
                    await asyncio.sleep(1)

            except asyncio.CancelledError:
                logger.info("📱 Polling de Telegram cancelado")
                break
            except Exception as e:
                logger.error(f"❌ Error en polling de Telegram: {e}")
                await asyncio.sleep(5)  # Pausa antes de reintentar

    def is_enabled(self):
        """Verifica si está habilitado"""
        return bool(self.bot_token)

    async def start_polling(self):
        """Inicia polling"""
        if not self.bot_token:
            logger.warning("⚠️ TELEGRAM_BOT_TOKEN no configurado - Telegram deshabilitado")
            return

        if self.running:
            logger.warning("⚠️ Polling de Telegram ya está ejecutándose")
            return

        self.running = True
        self.polling_task = asyncio.create_task(self._polling_loop())
        logger.info("🚀 Polling de Telegram iniciado con soporte para grupos")

    async def stop_polling(self):
        """Detiene polling"""
        self.running = False

        if self.polling_task:
            self.polling_task.cancel()
            try:
                await self.polling_task
            except asyncio.CancelledError:
                pass
            self.polling_task = None

        logger.info("🛑 Polling de Telegram detenido")

    def get_status(self):
        """Estado del adaptador"""
        return {
            "enabled": self.is_enabled(),
            "running": self.running,
            "has_token": bool(self.bot_token),
            "bot_username": self.bot_username,
            "supports_groups": True
        }