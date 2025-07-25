# app/adapters/whatsapp.py
import httpx
from typing import Dict
from ..core.agent import BotAgent
from ..core.config import settings


class WhatsAppAdapter:
    def __init__(self, agent: BotAgent):
        self.agent = agent
        self.verify_token = settings.WHATSAPP_VERIFY_TOKEN
        self.access_token = settings.WHATSAPP_ACCESS_TOKEN
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID

    async def handle_webhook(self, request: Dict):
        """Maneja webhooks de WhatsApp Business API"""

        # Verificación de webhook (GET request como dict)
        if "hub.mode" in request:
            if request.get("hub.verify_token") == self.verify_token:
                return int(request.get("hub.challenge", 0))
            return {"error": "Invalid verify token"}

        # Procesar mensajes entrantes
        entry = request.get("entry", [])
        if not entry:
            return {"status": "no_entry"}

        for change in entry[0].get("changes", []):
            if change.get("field") == "messages":
                value = change.get("value", {})
                messages = value.get("messages", [])

                for message in messages:
                    await self._process_whatsapp_message(message)

        return {"status": "ok"}

    async def _process_whatsapp_message(self, message: Dict):
        """Procesa un mensaje individual de WhatsApp"""

        if message.get("type") != "text":
            return  # Solo procesar mensajes de texto

        user_phone = message.get("from")
        text_content = message.get("text", {}).get("body", "")

        if not text_content or not user_phone:
            return

        # Generar respuesta usando el agente
        session_id = f"whatsapp_{user_phone}"
        response = await self.agent.process_message(
            message=text_content,
            session_id=session_id,
            platform="whatsapp",
            user_id=user_phone
        )

        # Enviar respuesta
        await self._send_whatsapp_message(user_phone, response)

    async def _send_whatsapp_message(self, phone_number: str, message: str):
        """Envía un mensaje de WhatsApp"""

        url = f"https://graph.facebook.com/v18.0/{self.phone_number_id}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {"body": message}
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers)
                return response.status_code == 200
        except Exception as e:
            print(f"Error enviando mensaje WhatsApp: {e}")
            return False