# app/adapters/whatsapp_api.py
import httpx
import asyncio
import logging
import re
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class WhatsAppAPIAdapter:
    def __init__(self, agent):
        self.agent = agent
        self.access_token = None
        self.phone_number_id = None
        self.verify_token = None
        self.base_url = "https://graph.facebook.com/v18.0"
        self.bot_phone_number = None

        # Importar configuración
        try:
            from app.core.config import settings
            self.access_token = settings.WHATSAPP_ACCESS_TOKEN
            self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
            self.verify_token = settings.WHATSAPP_VERIFY_TOKEN
        except ImportError:
            try:
                from ..core.config import settings
                self.access_token = settings.WHATSAPP_ACCESS_TOKEN
                self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
                self.verify_token = settings.WHATSAPP_VERIFY_TOKEN
            except ImportError:
                logger.error("No se pudo importar configuración")

    async def _get_bot_info(self):
        """Obtiene información del bot"""
        if not self.access_token or not self.phone_number_id:
            return False

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            url = f"{self.base_url}/{self.phone_number_id}"
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    result = response.json()
                    self.bot_phone_number = result.get("display_phone_number")
                    logger.info(f"✅ Bot WhatsApp: {self.bot_phone_number}")
                    return True

        except Exception as e:
            logger.error(f"Error obteniendo info del bot WhatsApp: {e}")

        return False

    def _is_bot_mentioned(self, message_text: str, context: Dict = None) -> bool:
        """Verifica si el bot fue mencionado en un grupo"""
        if not message_text:
            return False

        text_lower = message_text.lower().strip()

        # Patrones de mención para WhatsApp
        mention_patterns = [
            r'@bot\b',
            r'@asistente\b',
            r'@meshchile\b',
            r'^bot[,:\s]',
            r'^asistente[,:\s]',
            r'^hey bot\b',
            r'^hola bot\b'
        ]

        for pattern in mention_patterns:
            if re.search(pattern, text_lower):
                logger.info(f"🏷️ Detectada mención por patrón: {pattern}")
                return True

        return False

    def _is_reply_to_bot(self, message: Dict) -> bool:
        """Verifica si es respuesta a un mensaje del bot"""
        context = message.get("context", {})

        if context:
            # WhatsApp API proporciona el ID del mensaje al que se responde
            quoted_msg_id = context.get("id")
            from_phone = context.get("from")

            # Si responde a nuestro bot (mismo número)
            if from_phone == self.bot_phone_number:
                logger.info("💬 Detectada respuesta al bot")
                return True

        return False

    def _get_reply_context(self, message: Dict) -> str:
        """Obtiene el contexto del mensaje respondido"""
        context = message.get("context", {})

        if context and context.get("from") == self.bot_phone_number:
            # Obtener texto del mensaje citado si está disponible
            quoted_body = context.get("body", "")
            if quoted_body:
                return f"[Respondiendo a: {quoted_body[:100]}...]"

        return ""

    def _clean_mention_from_text(self, text: str) -> str:
        """Limpia las menciones del texto para procesamiento"""
        if not text:
            return text

        cleaned = re.sub(r'@bot\b', '', text, flags=re.IGNORECASE)
        cleaned = re.sub(r'@asistente\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'@meshchile\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'^bot[,:\s]+', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'^asistente[,:\s]+', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'^hey bot[,:\s]*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'^hola bot[,:\s]*', '', cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    def _sanitize_message(self, text: str) -> str:
        """Sanitiza el mensaje para WhatsApp"""
        if not text:
            return "Mensaje vacío"

        # WhatsApp tiene límite de 4096 caracteres
        if len(text) > 4000:
            text = text[:3950] + "\n\n... (mensaje truncado por longitud)"

        # Remover caracteres de control problemáticos
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

        # Limpiar múltiples saltos de línea
        text = re.sub(r'\n{4,}', '\n\n\n', text)

        return text

    def _get_session_id(self, from_phone: str, chat_type: str, group_id: str = None) -> str:
        """Genera session ID apropiado según el tipo de chat"""
        if chat_type == "individual":
            return f"whatsapp_api_private_{from_phone}"
        else:
            group_identifier = group_id or from_phone
            return f"whatsapp_api_group_{group_identifier}"

    def _determine_chat_type(self, message: Dict, contacts: List = None) -> tuple:
        """Determina el tipo de chat y extrae información"""
        from_phone = message.get("from", "")

        # WhatsApp grupos generalmente tienen formato especial
        # Grupos: XXXXXXXXXX-XXXXXXXXXX@g.us
        # Individuales: XXXXXXXXXX@c.us o similar

        if "-" in from_phone and "@g.us" in from_phone:
            chat_type = "group"
            group_id = from_phone

            # Obtener nombre del grupo si está en contacts
            group_name = "Grupo"
            if contacts:
                for contact in contacts:
                    if contact.get("wa_id") == from_phone:
                        group_name = contact.get("profile", {}).get("name", "Grupo")
                        break

            return chat_type, group_id, group_name
        else:
            return "individual", None, "Chat privado"

    async def handle_webhook(self, request: Dict):
        """Maneja webhooks de WhatsApp Business API"""

        # Verificación de webhook (GET request)
        if "hub.mode" in request:
            if request.get("hub.verify_token") == self.verify_token:
                challenge = request.get("hub.challenge", "")
                logger.info("✅ Webhook verificado exitosamente")
                return int(challenge) if challenge.isdigit() else challenge
            else:
                logger.error("❌ Token de verificación inválido")
                return {"error": "Invalid verify token"}

        # Procesar mensajes entrantes
        entry = request.get("entry", [])
        if not entry:
            return {"status": "no_entry"}

        for entry_item in entry:
            changes = entry_item.get("changes", [])
            for change in changes:
                if change.get("field") == "messages":
                    await self._process_webhook_change(change.get("value", {}))

        return {"status": "ok"}

    async def _process_webhook_change(self, value: Dict):
        """Procesa cambios en mensajes del webhook"""
        messages = value.get("messages", [])
        contacts = value.get("contacts", [])

        for message in messages:
            await self._process_message(message, contacts)

    async def _process_message(self, message: Dict, contacts: List):
        """Procesa un mensaje individual con soporte para grupos"""
        try:
            from_phone = message.get("from")
            message_id = message.get("id")
            timestamp = message.get("timestamp")

            if not from_phone:
                return

            # Determinar tipo de chat
            chat_type, group_id, chat_title = self._determine_chat_type(message, contacts)

            # Solo procesar mensajes de texto por ahora
            if message.get("type") != "text":
                return

            text_content = message.get("text", {}).get("body", "")
            if not text_content:
                return

            # Obtener info del usuario
            user_name = "Usuario"
            user_phone = from_phone

            # En grupos, el 'from' es del usuario individual, no del grupo
            if contacts:
                for contact in contacts:
                    if contact.get("wa_id") == from_phone:
                        user_name = contact.get("profile", {}).get("name", "Usuario")
                        break

            # Log del mensaje
            chat_info = f"({chat_type})" if chat_type == "individual" else f"({chat_type}: {chat_title})"
            logger.info(f"📨 WhatsApp API {chat_info} - {user_name}: {text_content[:50]}...")

            # Lógica diferente según tipo de chat
            if chat_type == "individual":
                await self._handle_private_message(message, from_phone, user_name, text_content)
            elif chat_type == "group":
                await self._handle_group_message(
                    message, from_phone, user_name, text_content,
                    chat_title, group_id
                )

        except Exception as e:
            logger.error(f"❌ Error procesando mensaje de WhatsApp API: {e}")

            if 'from_phone' in locals():
                error_response = "Disculpa, tuve un problema procesando tu mensaje. ¿Puedes intentar de nuevo?"
                await self._send_message(from_phone, error_response)

    async def _handle_private_message(self, message: Dict, from_phone: str, user_name: str, text: str):
        """Maneja mensajes en chat privado"""

        # Comandos especiales
        if text.lower() in ["hola", "/start", "start", "ayuda", "help"]:
            welcome = f"¡Hola {user_name}! 👋\n\n🔗 Soy el asistente FAQ de la comunidad **MeshChile Meshtastic**.\n\nPuedes preguntarme sobre:\n• Configuración de nodos\n• Integraciones disponibles\n• Funciones de la comunidad\n• Soporte técnico\n\nSolo escríbeme tu pregunta normalmente."
            await self._send_message(from_phone, welcome)
            return

        if not text or len(text.strip()) < 2:
            await self._send_message(from_phone, "¿Tienes alguna pregunta sobre Meshtastic o la comunidad MeshChile?")
            return

        # Procesar con el agente
        await self._process_with_agent(from_phone, from_phone, user_name, text, "individual", message)

    async def _handle_group_message(self, message: Dict, from_phone: str, user_name: str,
                                    text: str, chat_title: str, group_id: str):
        """Maneja mensajes en grupos"""

        # Verificar si el bot fue mencionado O si es respuesta al bot
        is_mentioned = self._is_bot_mentioned(text, message)
        is_reply = self._is_reply_to_bot(message)

        if not is_mentioned and not is_reply:
            return

        interaction_type = "mención" if is_mentioned else "respuesta"
        logger.info(f"🏷️ Bot activado por {interaction_type} en grupo '{chat_title}' por {user_name}")

        # Limpiar menciones del texto para procesamiento
        clean_text = self._clean_mention_from_text(text).strip()

        # Comandos especiales en grupos
        if clean_text.lower() in ["/start", "start", "hola", "ayuda", "help"]:
            welcome = f"¡Hola {user_name}! 👋\n\n🔗 Soy el bot FAQ de **MeshChile Meshtastic**.\n\n📱 **En grupos**: Mencioname con @bot o responde a mis mensajes\n\n💬 **Chat privado**: Escríbeme directo\n\n🤖 Pregúntame sobre configuración, integraciones, cobertura, etc."
            await self._send_message(group_id, welcome)
            return

        if not clean_text:
            await self._send_message(group_id, f"{user_name}, ¿en qué puedo ayudarte con Meshtastic? 🔗")
            return

        # Procesar pregunta en grupo
        await self._process_with_agent(group_id, group_id, user_name, clean_text, "group", message, chat_title)

    async def _process_with_agent(self, to_phone: str, session_base: str, user_name: str,
                                  text: str, chat_type: str, message: Dict, chat_title: str = None):
        """Procesa el mensaje con el agente"""
        try:
            # Generar session ID apropiado
            session_id = self._get_session_id(session_base, chat_type, session_base if chat_type == "group" else None)

            # Agregar contexto de respuesta si aplica
            reply_context = self._get_reply_context(message)
            if reply_context:
                text = f"{reply_context}\n\n{text}"

            # Contexto adicional para el prompt
            context_info = f"Usuario: {user_name}"
            if chat_type == "group" and chat_title:
                context_info += f" (en grupo: {chat_title})"

            # Procesar con el agente
            response = await self.agent.process_message(
                message=text,
                session_id=session_id,
                platform=f"whatsapp_api_{chat_type}",
                user_id=user_name
            )

            # En grupos, mencionar al usuario en la respuesta
            if chat_type == "group":
                response = f"{user_name}, {response}"

            # Sanitizar mensaje antes de enviar
            response = self._sanitize_message(response)

            # Enviar respuesta
            await self._send_message(to_phone, response)
            logger.info(f"✅ Respuesta enviada a {user_name} en {chat_type}")

        except Exception as e:
            logger.error(f"❌ Error procesando con agente: {e}")
            error_response = "Disculpa, tuve un problema procesando tu pregunta sobre Meshtastic. ¿Puedes intentar de nuevo?"

            if chat_type == "group":
                error_response = f"{user_name}, {error_response}"

            await self._send_message(to_phone, error_response)

    async def _send_message(self, to_phone: str, message: str):
        """Envía un mensaje a WhatsApp"""
        if not self.access_token or not self.phone_number_id:
            logger.error("❌ Configuración de WhatsApp API incompleta")
            return False

        url = f"{self.base_url}/{self.phone_number_id}/messages"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": message}
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code == 200:
                    return True
                else:
                    error_msg = response.text
                    logger.error(f"❌ Error enviando mensaje WhatsApp API: {response.status_code} - {error_msg}")
                    return False

        except Exception as e:
            logger.error(f"❌ Error de conexión enviando mensaje WhatsApp API: {e}")
            return False

    def is_enabled(self):
        """Verifica si está habilitado"""
        return bool(self.access_token and self.phone_number_id and self.verify_token)

    async def initialize(self):
        """Inicializa el adaptador"""
        if not self.is_enabled():
            logger.warning("⚠️ WhatsApp Business API no configurado completamente")
            return False

        # Obtener info del bot
        success = await self._get_bot_info()
        if success:
            logger.info("✅ WhatsApp Business API adapter inicializado")

        return success

    def get_status(self):
        """Estado del adaptador"""
        return {
            "enabled": self.is_enabled(),
            "method": "official_api",
            "has_access_token": bool(self.access_token),
            "has_phone_number_id": bool(self.phone_number_id),
            "has_verify_token": bool(self.verify_token),
            "bot_phone_number": self.bot_phone_number,
            "supports_groups": True
        }