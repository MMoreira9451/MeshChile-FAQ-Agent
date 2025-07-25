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
                        self.bot_id = bot_info.get("id")  # IMPORTANTE para detectar respuestas
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
        if not self.bot_username or not text:
            return text

        # Remover @username del texto
        mention_pattern = f"@{self.bot_username}"
        cleaned_text = re.sub(
            re.escape(mention_pattern),
            "",
            text,
            flags=re.IGNORECASE
        ).strip()

        # Limpiar espacios múltiples
        cleaned_text = " ".join(cleaned_text.split())

        return cleaned_text

    def _sanitize_message(self, text: str) -> str:
        """Sanitiza el mensaje para evitar problemas con Telegram"""
        if not text:
            return "Mensaje vacío"

        # Limitar longitud (Telegram tiene límite de 4096 caracteres)
        if len(text) > 4000:
            text = text[:3950] + "\n\n... (mensaje truncado por longitud)"

        # Remover caracteres de control problemáticos
        # Remover caracteres de control excepto \n y \t
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

        # Limpiar múltiples saltos de línea
        text = re.sub(r'\n{4,}', '\n\n\n', text)

        return text

    def _get_session_id(self, chat_id: int, user_id: int, chat_type: str,
                        message_thread_id: Optional[int] = None) -> str:
        """Genera session ID apropiado según el tipo de chat y thread"""
        if chat_type == "private":
            # Chat privado: sesión individual
            return f"telegram_private_{chat_id}_{user_id}"
        else:
            # Grupo/supergrupo: incluir thread_id si existe
            if message_thread_id:
                # Sesión por thread específico en supergrupo con temas
                return f"telegram_group_{chat_id}_thread_{message_thread_id}"
            else:
                # Grupo normal: sesión por grupo (compartida)
                return f"telegram_group_{chat_id}"

    async def handle_webhook(self, request: Dict):
        """Maneja webhooks de Telegram (para compatibilidad)"""
        message = request.get("message")
        if not message:
            return {"status": "no_message"}

        await self._process_message(message)
        return {"status": "ok"}

    async def _process_message(self, message: Dict):
        """Procesa un mensaje individual con soporte para grupos y threads"""
        try:
            # Extraer información del mensaje
            chat = message.get("chat", {})
            chat_id = chat.get("id")
            chat_type = chat.get("type", "private")
            chat_title = chat.get("title", "")

            # CAPTURAR message_thread_id para temas en supergrupos
            message_thread_id = message.get("message_thread_id")

            user = message.get("from", {})
            user_id = user.get("id")
            user_name = user.get("first_name", "Usuario")
            username = user.get("username", "")

            text = message.get("text", "")
            entities = message.get("entities", [])
            reply_to_message = message.get("reply_to_message")

            # DEBUG: Log detallado del mensaje recibido
            logger.info(f"🔍 DEBUG _process_message:")
            logger.info(f"  📍 chat_id: {chat_id}")
            logger.info(f"  📍 chat_type: {chat_type}")
            logger.info(f"  📍 chat_title: '{chat_title}'")
            logger.info(f"  🧵 message_thread_id: {message_thread_id}")  # NUEVO
            logger.info(f"  👤 user_name: {user_name}")
            logger.info(f"  💬 text: {text[:50]}...")

            if not chat_id or not user_id:
                logger.error(f"❌ chat_id o user_id faltante: chat_id={chat_id}, user_id={user_id}")
                return

            # Log del mensaje con info de thread
            thread_info = f" [thread:{message_thread_id}]" if message_thread_id else ""
            chat_info = f"({chat_type})" if chat_type == "private" else f"({chat_type}: {chat_title}{thread_info})"
            logger.info(f"📨 Telegram {chat_info} - {user_name}: {text[:50]}...")

            # Lógica diferente según tipo de chat
            if chat_type == "private":
                await self._handle_private_message(message, chat_id, user_id, user_name, text)
            elif chat_type in ["group", "supergroup"]:
                await self._handle_group_message(
                    message, chat_id, user_id, user_name, text, entities,
                    chat_title, reply_to_message, message_thread_id  # PASAR thread_id
                )
            else:
                logger.info(f"ℹ️ Ignorando mensaje de tipo: {chat_type}")
                return

        except Exception as e:
            logger.error(f"❌ Error procesando mensaje de Telegram: {e}")
            if 'chat_id' in locals():
                error_response = "Disculpa, tuve un problema procesando tu mensaje. ¿Puedes intentar de nuevo?"
                # Enviar con thread_id si existe
                await self._send_message(chat_id, error_response, message_thread_id=locals().get('message_thread_id'))

    async def _handle_private_message(self, message: Dict, chat_id: int, user_id: int, user_name: str, text: str):
        """Maneja mensajes privados"""
        logger.info(f"💬 Mensaje privado de {user_name}: {text[:50]}...")

        # En mensajes privados no hay threads
        await self._process_with_agent(chat_id, user_id, user_name, text, "private")

    async def _handle_group_message(self, message: Dict, chat_id: int, user_id: int, user_name: str, text: str,
                                    entities: List[Dict], chat_title: str, reply_to_message: Dict = None,
                                    message_thread_id: Optional[int] = None):  # NUEVO PARÁMETRO
        """Maneja mensajes en grupos con soporte para threads"""

        # DEBUG: Log del chat_id y thread_id recibido
        logger.info(f"🔍 DEBUG _handle_group_message:")
        logger.info(f"  📍 chat_id recibido: {chat_id}")
        logger.info(f"  📍 chat_title: '{chat_title}'")
        logger.info(f"  🧵 message_thread_id: {message_thread_id}")  # NUEVO

        # VERIFICACIÓN ADICIONAL: Asegurar que el chat_id es correcto
        original_chat_id = message.get("chat", {}).get("id")
        original_chat_title = message.get("chat", {}).get("title", "")
        original_thread_id = message.get("message_thread_id")  # VERIFICAR thread_id también

        logger.info(f"🔍 DEBUG verificación:")
        logger.info(f"  📍 original_chat_id del message: {original_chat_id}")
        logger.info(f"  📍 original_chat_title del message: '{original_chat_title}'")
        logger.info(f"  🧵 original_thread_id del message: {original_thread_id}")  # NUEVO

        if chat_id != original_chat_id:
            logger.error(f"🚨 PROBLEMA DETECTADO: chat_id no coincide!")
            logger.error(f"  ❌ Parámetro chat_id: {chat_id}")
            logger.error(f"  ✅ Original chat_id: {original_chat_id}")
            logger.error(f"  🔄 CORRIGIENDO: usando original_chat_id")
            chat_id = original_chat_id  # Forzar el correcto
            chat_title = original_chat_title
            message_thread_id = original_thread_id  # Corregir thread_id también

        # Verificar si el bot fue mencionado O si es respuesta al bot
        if not self._is_bot_mentioned(text, entities, reply_to_message):
            return

        # Determinar el tipo de interacción
        interaction_type = "mención"
        if reply_to_message:
            reply_from = reply_to_message.get("from", {})
            if reply_from.get("id") == self.bot_id:
                interaction_type = "respuesta"

        # Log con info de thread
        thread_info = f" en thread {message_thread_id}" if message_thread_id else ""
        logger.info(f"🏷️ Bot activado por {interaction_type} en grupo '{chat_title}'{thread_info} por {user_name}")

        # Limpiar menciones del texto para procesamiento
        clean_text = self._clean_mention_from_text(text).strip()

        # Comandos especiales en grupos
        if clean_text.lower() in ["/start", "start", "hola", "ayuda", "help"]:
            welcome = f"¡Hola {user_name}! 👋\n\n🔗 Soy el bot FAQ de **MeshChile Meshtastic**.\n\n📱 **En grupos**:\n• Mencioname: @{self.bot_username} tu pregunta\n• O responde a mis mensajes\n\n💬 **Chat privado**: Escríbeme directo\n\n🤖 Pregúntame sobre configuración, integraciones, cobertura, etc."

            # Enviar con thread_id si existe
            logger.info(f"🔍 DEBUG enviando welcome a chat_id: {chat_id}, thread: {message_thread_id}")
            await self._send_message(chat_id, welcome, message_thread_id=message_thread_id)
            return

        if not clean_text:
            response = f"{user_name}, ¿en qué puedo ayudarte con Meshtastic? 🔗"
            # Enviar con thread_id si existe
            logger.info(f"🔍 DEBUG enviando respuesta vacía a chat_id: {chat_id}, thread: {message_thread_id}")
            await self._send_message(chat_id, response, message_thread_id=message_thread_id)
            return

        # DEBUG: Log antes de procesar con agente
        logger.info(f"🔍 DEBUG antes de _process_with_agent:")
        logger.info(f"  📍 chat_id: {chat_id}")
        logger.info(f"  📍 chat_title: '{chat_title}'")
        logger.info(f"  🧵 message_thread_id: {message_thread_id}")  # NUEVO

        # Procesar pregunta en grupo con thread_id
        await self._process_with_agent(chat_id, user_id, user_name, clean_text, "group", chat_title, message_thread_id)

    async def _process_with_agent(self, chat_id: int, user_id: int, user_name: str, text: str, chat_type: str,
                                  chat_title: str = None, message_thread_id: Optional[int] = None):  # NUEVO PARÁMETRO
        """Procesa el mensaje con el agente incluyendo soporte para threads"""
        try:
            # DEBUG: Log detallado de entrada
            logger.info(f"🔍 DEBUG _process_with_agent:")
            logger.info(f"  📍 chat_id: {chat_id}")
            logger.info(f"  👤 user_name: {user_name}")
            logger.info(f"  📱 chat_type: {chat_type}")
            logger.info(f"  📍 chat_title: '{chat_title}'")
            logger.info(f"  🧵 message_thread_id: {message_thread_id}")  # NUEVO
            logger.info(f"  💬 text: {text[:50]}...")

            # Mostrar que está escribiendo
            await self._send_typing_action(chat_id, message_thread_id)  # Pasar thread_id

            # Generar session ID incluyendo thread_id
            session_id = self._get_session_id(chat_id, user_id, chat_type, message_thread_id)
            logger.info(f"🔍 DEBUG session_id generado: {session_id}")

            # Contexto adicional para el prompt
            context_info = f"Usuario: {user_name}"
            if chat_type == "group" and chat_title:
                thread_info = f" (thread {message_thread_id})" if message_thread_id else ""
                context_info += f" (en grupo: {chat_title}{thread_info})"

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

            # Sanitizar mensaje antes de enviar
            response = self._sanitize_message(response)

            # DEBUG: Log antes de enviar respuesta final
            logger.info(f"🔍 DEBUG antes de enviar respuesta final:")
            logger.info(f"  📍 chat_id: {chat_id}")
            logger.info(f"  🧵 message_thread_id: {message_thread_id}")  # NUEVO
            logger.info(f"  💬 response: {response[:100]}...")

            # Enviar respuesta con thread_id si existe
            await self._send_message(chat_id, response, message_thread_id=message_thread_id)

            thread_info = f" en thread {message_thread_id}" if message_thread_id else ""
            logger.info(f"✅ Respuesta enviada a {user_name} en {chat_type}{thread_info}")

        except Exception as e:
            logger.error(f"❌ Error procesando con agente: {e}")
            error_response = "Disculpa, tuve un problema procesando tu pregunta sobre Meshtastic. ¿Puedes intentar de nuevo?"

            if chat_type == "group":
                error_response = f"{user_name}, {error_response}"

            # Enviar error con thread_id si existe
            logger.info(f"🔍 DEBUG enviando error a chat_id: {chat_id}, thread: {message_thread_id}")
            await self._send_message(chat_id, error_response, message_thread_id=message_thread_id)

    async def _send_message(self, chat_id: int, text: str, parse_mode: str = None,
                            message_thread_id: Optional[int] = None):  # NUEVO PARÁMETRO
        """Envía un mensaje a Telegram con manejo robusto de errores y soporte para threads"""

        # DEBUG: Log crítico del envío
        logger.info(f"🔍 DEBUG _send_message:")
        logger.info(f"  📍 chat_id FINAL: {chat_id}")
        logger.info(f"  🧵 message_thread_id: {message_thread_id}")  # NUEVO
        logger.info(f"  💬 text (primeros 50): {text[:50]}...")

        if not self.base_url:
            logger.error("❌ No se puede enviar mensaje: bot_token no configurado")
            return False

        url = f"{self.base_url}/sendMessage"

        # Función para escapar caracteres de Markdown
        def escape_markdown(text: str) -> str:
            """Escapa caracteres especiales de Markdown V2"""
            special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
            for char in special_chars:
                text = text.replace(char, f'\\{char}')
            return text

        # Intentar enviar con diferentes modos de parse
        attempts = [
            {"parse_mode": None, "text": text},
            {"parse_mode": "HTML", "text": text.replace("**", "<b>").replace("**", "</b>")},
            {"parse_mode": "MarkdownV2", "text": escape_markdown(text)},
        ]

        for attempt in attempts:
            payload = {
                "chat_id": chat_id,
                "text": attempt["text"]
            }

            if attempt["parse_mode"]:
                payload["parse_mode"] = attempt["parse_mode"]

            # INCLUIR message_thread_id si existe (para responder en el thread correcto)
            if message_thread_id:
                payload["message_thread_id"] = message_thread_id

            # DEBUG: Log del payload final
            logger.info(f"🔍 DEBUG payload enviado a Telegram:")
            logger.info(f"  📍 chat_id en payload: {payload['chat_id']}")
            logger.info(f"  🧵 message_thread_id en payload: {payload.get('message_thread_id', 'None')}")  # NUEVO

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(url, json=payload)

                    if response.status_code == 200:
                        thread_info = f" en thread {message_thread_id}" if message_thread_id else ""
                        logger.info(f"✅ Mensaje enviado exitosamente a chat_id: {chat_id}{thread_info}")
                        return True
                    else:
                        error_msg = response.text
                        logger.warning(f"Intento falló: {response.status_code} - {error_msg}")
                        if attempt == attempts[-1]:
                            logger.error(
                                f"Error enviando mensaje (todos los intentos fallaron): {response.status_code} - {error_msg}")
                        continue

            except Exception as e:
                logger.warning(f"Error de conexión: {e}")
                continue

        logger.error(f"❌ No se pudo enviar mensaje después de {len(attempts)} intentos")
        return False

    async def _send_typing_action(self, chat_id: int, message_thread_id: Optional[int] = None):  # NUEVO PARÁMETRO
        """Envía acción de 'escribiendo' con soporte para threads"""
        if not self.base_url:
            return

        url = f"{self.base_url}/sendChatAction"

        payload = {
            "chat_id": chat_id,
            "action": "typing"
        }

        # INCLUIR message_thread_id si existe
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id

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
        logger.info("🚀 Polling de Telegram iniciado con soporte para grupos y threads")

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
            "supports_groups": True,
            "supports_threads": True  # NUEVO
        }