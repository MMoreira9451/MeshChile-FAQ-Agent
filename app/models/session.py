# app/models/session.py
import redis
import json
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from ..core.config import settings


class RedisSessionManager:
    def __init__(self):
        """Inicializa el gestor de sesiones con Redis"""
        try:
            # Crear conexión a Redis
            self.redis_client = redis.from_url(
                settings.redis_full_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )

            # Probar conexión
            self.redis_client.ping()
            print(f"✅ Conectado a Redis: {settings.redis_full_url}")

        except redis.ConnectionError as e:
            print(f"❌ Error conectando a Redis: {e}")
            print(f"🔧 Verifica que Redis esté corriendo en: {settings.redis_full_url}")
            raise
        except Exception as e:
            print(f"❌ Error inesperado con Redis: {e}")
            raise

        self.session_ttl = settings.SESSION_TTL
        self.max_messages = settings.MAX_SESSION_MESSAGES

    def _get_session_key(self, session_id: str) -> str:
        """Genera clave para la sesión en Redis"""
        return f"bot_session:{session_id}"

    async def get_context(self, session_id: str) -> List[Dict]:
        """Obtiene el contexto de una sesión desde Redis"""
        try:
            session_key = self._get_session_key(session_id)
            data = self.redis_client.get(session_key)

            if data:
                context = json.loads(data)
                return context if isinstance(context, list) else []

            return []

        except json.JSONDecodeError as e:
            print(f"❌ Error decodificando JSON para sesión {session_id}: {e}")
            # Limpiar sesión corrupta
            await self.clear_session(session_id)
            return []
        except redis.RedisError as e:
            print(f"❌ Error Redis obteniendo contexto {session_id}: {e}")
            return []
        except Exception as e:
            print(f"❌ Error inesperado obteniendo contexto {session_id}: {e}")
            return []

    async def add_message(self, session_id: str, message: Dict):
        """Añade un mensaje al contexto de la sesión en Redis"""
        try:
            # Añadir timestamp si no existe
            if "timestamp" not in message:
                message["timestamp"] = datetime.now().isoformat()

            # Obtener contexto actual
            context = await self.get_context(session_id)

            # Añadir nuevo mensaje
            context.append(message)

            # Mantener solo los últimos N mensajes
            if len(context) > self.max_messages:
                context = context[-self.max_messages:]

            # Guardar en Redis con TTL
            session_key = self._get_session_key(session_id)
            self.redis_client.setex(
                session_key,
                self.session_ttl,
                json.dumps(context, ensure_ascii=False)
            )

        except redis.RedisError as e:
            print(f"❌ Error Redis guardando mensaje en {session_id}: {e}")
        except Exception as e:
            print(f"❌ Error guardando mensaje en sesión {session_id}: {e}")

    async def clear_session(self, session_id: str):
        """Limpia una sesión específica"""
        try:
            session_key = self._get_session_key(session_id)
            result = self.redis_client.delete(session_key)
            return result > 0
        except redis.RedisError as e:
            print(f"❌ Error Redis limpiando sesión {session_id}: {e}")
            return False
        except Exception as e:
            print(f"❌ Error limpiando sesión {session_id}: {e}")
            return False

    async def get_session_info(self, session_id: str) -> Dict:
        """Obtiene información detallada de la sesión"""
        try:
            context = await self.get_context(session_id)
            session_key = self._get_session_key(session_id)

            # Obtener TTL restante
            ttl = self.redis_client.ttl(session_key)

            # Contar mensajes por tipo
            user_messages = len([m for m in context if m.get("role") == "user"])
            assistant_messages = len([m for m in context if m.get("role") == "assistant"])

            # Obtener plataformas usadas
            platforms = list(set([m.get("platform", "unknown") for m in context if "platform" in m]))

            # Última actividad
            last_activity = None
            if context:
                last_message = context[-1]
                last_activity = last_message.get("timestamp")

            return {
                "session_id": session_id,
                "message_count": len(context),
                "user_messages": user_messages,
                "assistant_messages": assistant_messages,
                "platforms": platforms,
                "last_activity": last_activity,
                "ttl_seconds": ttl if ttl > 0 else None,
                "exists": len(context) > 0
            }

        except Exception as e:
            print(f"❌ Error obteniendo info de sesión {session_id}: {e}")
            return {
                "session_id": session_id,
                "message_count": 0,
                "user_messages": 0,
                "assistant_messages": 0,
                "platforms": [],
                "last_activity": None,
                "ttl_seconds": None,
                "exists": False,
                "error": str(e)
            }

    async def list_active_sessions(self, pattern: str = "bot_session:*") -> List[str]:
        """Lista todas las sesiones activas"""
        try:
            keys = self.redis_client.keys(pattern)
            # Extraer solo los session_ids
            session_ids = [key.replace("bot_session:", "") for key in keys]
            return session_ids
        except redis.RedisError as e:
            print(f"❌ Error Redis listando sesiones: {e}")
            return []
        except Exception as e:
            print(f"❌ Error listando sesiones: {e}")
            return []

    async def cleanup_expired_sessions(self):
        """Limpia sesiones expiradas (Redis lo hace automáticamente, pero útil para estadísticas)"""
        try:
            active_sessions = await self.list_active_sessions()
            print(f"📊 Sesiones activas: {len(active_sessions)}")
            return len(active_sessions)
        except Exception as e:
            print(f"❌ Error en cleanup: {e}")
            return 0

    def health_check(self) -> Dict:
        """Verifica el estado de Redis"""
        try:
            # Ping a Redis
            ping_result = self.redis_client.ping()

            # Info básica
            info = self.redis_client.info()

            return {
                "status": "healthy" if ping_result else "unhealthy",
                "ping": ping_result,
                "connected_clients": info.get("connected_clients", "unknown"),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "redis_version": info.get("redis_version", "unknown"),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0)
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "ping": False
            }