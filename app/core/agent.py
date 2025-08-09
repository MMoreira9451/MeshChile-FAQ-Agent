# app/core/agent.py
import json
from typing import Dict, List, Optional
from datetime import datetime
from .openwebui_client import MenthaClient
from ..models.session import RedisSessionManager


class BotAgent:
    def __init__(self):
        """Inicializa el agente con OpenWebUI y Redis"""
        self.openwebui_client = MenthaClient()
        self.session_manager = RedisSessionManager()

        # System prompt por defecto
        self.default_system_prompt = """Eres Mentha, una inteligencia artificial cercana, empática y confiable, entrenada para asistir a estudiantes.

Utilizas una base de conocimiento especializada sobre burnout académico y salud mental estudiantil, y siempre respondes de forma precisa, empática y fundamentada en los documentos disponibles.

Tu personalidad:
- Cercana y empática
- Confiable y profesional
- Comprensiva con las dificultades estudiantiles
- Orientada al bienestar mental y académico

Especializaciones:
- Burnout académico y prevención
- Estrategias de manejo del estrés
- Técnicas de estudio efectivas
- Apoyo emocional para estudiantes
- Equilibrio vida académica-personal

Formato de respuesta:
- Respuestas claras y bien estructuradas
- Lenguaje comprensible y cercano
- Incluir estrategias prácticas cuando sea apropiado
- Mostrar empatía y comprensión
- Fundamentar consejos en la base de conocimiento disponible"""

    async def process_message(
            self,
            message: str,
            session_id: str,
            platform: str = "api",
            user_id: Optional[str] = None,
            system_prompt: Optional[str] = None
    ) -> str:
        """Procesa un mensaje y genera una respuesta"""

        try:
            # 1. Obtener contexto de la sesión desde Redis
            session_context = await self.session_manager.get_context(session_id)

            # 2. Preparar mensajes para el modelo
            messages = []

            # System prompt
            final_system_prompt = system_prompt or self.default_system_prompt
            messages.append({"role": "system", "content": final_system_prompt})

            # Contexto de conversación (últimos intercambios)
            recent_context = session_context[-10:] if len(session_context) > 10 else session_context
            for msg in recent_context:
                if msg.get("role") in ["user", "assistant"]:
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })

            # Mensaje actual del usuario
            messages.append({"role": "user", "content": message})

            # 3. Generar respuesta usando OpenWebUI
            response = await self.mentha_client.chat_completion(messages)

            # 4. Guardar intercambio en Redis
            timestamp = datetime.now().isoformat()

            # Guardar mensaje del usuario
            await self.session_manager.add_message(
                session_id,
                {
                    "role": "user",
                    "content": message,
                    "platform": platform,
                    "user_id": user_id,
                    "timestamp": timestamp
                }
            )

            # Guardar respuesta del asistente
            await self.session_manager.add_message(
                session_id,
                {
                    "role": "assistant",
                    "content": response,
                    "platform": platform,
                    "timestamp": timestamp
                }
            )

            return response

        except Exception as e:
            error_msg = f"Error procesando mensaje: {str(e)}"
            print(error_msg)

            # Respuesta de error amigable
            return "Lo siento, hubo un problema procesando tu mensaje. Por favor inténtalo de nuevo en unos momentos."

    async def get_session_summary(self, session_id: str) -> Dict:
        """Obtiene un resumen completo de la sesión"""
        return await self.session_manager.get_session_info(session_id)

    async def clear_conversation(self, session_id: str) -> bool:
        """Limpia la conversación de una sesión"""
        return await self.session_manager.clear_session(session_id)

    async def list_active_sessions(self) -> List[str]:
        """Lista todas las sesiones activas"""
        return await self.session_manager.list_active_sessions()

    async def health_check(self) -> Dict:
        """Verifica el estado completo del agente"""

        # Check OpenWebUI
        openwebui_health = await self.openwebui_client.health_check()

        # Check Redis
        redis_health = self.session_manager.health_check()

        # Estado general
        overall_healthy = (
                openwebui_health.get("status") == "healthy" and
                redis_health.get("status") == "healthy"
        )

        return {
            "status": "healthy" if overall_healthy else "unhealthy",
            "components": {
                "openwebui": openwebui_health,
                "redis": redis_health
            },
            "session_manager": {
                "active_sessions": len(await self.list_active_sessions())
            }
        }