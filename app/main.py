# app/main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
import asyncio
from typing import List
from .core.agent import BotAgent
from .models.message import MessageRequest, MessageResponse, SessionInfo, HealthResponse
from .core.config import settings

# Configurar logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Crear aplicación FastAPI
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    debug=settings.API_DEBUG,
    description="Backend universal para bot multi-plataforma con Open Web UI, Redis y Telegram integrado"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instancias globales
agent: BotAgent = None
telegram_manager = None


@app.on_event("startup")
async def startup_event():
    """Inicialización al arrancar - incluye Telegram automáticamente"""
    global agent, telegram_manager
    logger.info("🚀 Iniciando Bot Agent con Telegram integrado...")

    print(f"📡 API: {settings.API_HOST}:{settings.API_PORT}")
    print(f"🔗 Open Web UI: {settings.OPENWEBUI_BASE_URL}")
    print(f"🤖 Modelo: {settings.MODEL_NAME}")
    print(f"💾 Redis: {settings.redis_full_url}")

    try:
        # Inicializar agente principal
        agent = BotAgent()
        logger.info("✅ Bot Agent inicializado")

        # Inicializar Telegram automáticamente
        if settings.TELEGRAM_BOT_TOKEN:
            logger.info("📱 Inicializando Telegram...")
            from .core.telegram_manager import TelegramManager

            telegram_manager = TelegramManager(agent)
            await telegram_manager.initialize()
        else:
            logger.info("ℹ️ Telegram no configurado (TELEGRAM_BOT_TOKEN faltante)")

        # Verificar conectividad general
        health = await agent.health_check()
        if health["status"] != "healthy":
            logger.warning(f"⚠️ Algunos componentes no están saludables: {health}")
        else:
            logger.info("✅ Todos los componentes están saludables")

        print("\n🎉 ¡Bot Agent listo!")
        if telegram_manager and telegram_manager.get_status().get("status") == "running":
            print("📱 Telegram: ✅ Activo y funcionando")
            print("💡 Busca tu bot en Telegram y empieza a chatear")
        else:
            print("📱 Telegram: ⚠️ No configurado")
        print()

    except Exception as e:
        logger.error(f"❌ Error inicializando Bot Agent: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Limpieza al cerrar - incluye Telegram"""
    global telegram_manager
    logger.info("👋 Cerrando Bot Agent...")

    # Cerrar Telegram si está activo
    if telegram_manager:
        await telegram_manager.shutdown()


def get_agent() -> BotAgent:
    """Dependency para obtener la instancia del agente"""
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent


@app.get("/")
async def root():
    """Endpoint raíz con información del servicio"""
    telegram_status = "disabled"
    if telegram_manager:
        status = telegram_manager.get_status()
        telegram_status = status.get("status", "unknown")

    platforms_enabled = {
        "telegram": {
            "configured": bool(settings.TELEGRAM_BOT_TOKEN),
            "status": telegram_status,
            "method": "polling" if settings.TELEGRAM_BOT_TOKEN else "none"
        },
        "whatsapp": {
            "configured": bool(settings.WHATSAPP_ACCESS_TOKEN),
            "method": "webhook" if settings.WHATSAPP_ACCESS_TOKEN else "none"
        },
        "discord": {
            "configured": bool(settings.DISCORD_BOT_TOKEN),
            "method": "webhook" if settings.DISCORD_BOT_TOKEN else "none"
        }
    }

    return {
        "message": f"{settings.API_TITLE} is running",
        "version": settings.API_VERSION,
        "model": settings.MODEL_NAME,
        "openwebui_url": settings.OPENWEBUI_BASE_URL,
        "platforms": platforms_enabled,
        "endpoints": {
            "chat": "/chat",
            "health": "/health",
            "docs": "/docs",
            "sessions": "/sessions",
            "telegram_status": "/telegram/status"
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health_check(agent: BotAgent = Depends(get_agent)):
    """Health check completo del sistema incluyendo Telegram"""
    try:
        health = await agent.health_check()

        # Añadir estado de Telegram
        if telegram_manager:
            telegram_status = telegram_manager.get_status()
            health["components"]["telegram"] = {
                "status": "healthy" if telegram_status.get("status") == "running" else "inactive",
                "enabled": telegram_status.get("enabled", False),
                "running": telegram_status.get("running", False)
            }
        else:
            health["components"]["telegram"] = {
                "status": "disabled",
                "enabled": False,
                "running": False
            }

        # El sistema está saludable si los componentes core están bien
        # Telegram es opcional
        core_healthy = (
                health["components"]["openwebui"]["status"] == "healthy" and
                health["components"]["redis"]["status"] == "healthy"
        )

        if not core_healthy:
            raise HTTPException(status_code=503, detail="Core services unhealthy")

        return HealthResponse(**health)

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Health check failed: {str(e)}")


@app.get("/telegram/status")
async def get_telegram_status():
    """Estado específico de Telegram"""
    if not telegram_manager:
        return {
            "status": "not_initialized",
            "enabled": False,
            "message": "Telegram manager not initialized"
        }

    status = telegram_manager.get_status()

    return {
        "telegram": status,
        "token_configured": bool(settings.TELEGRAM_BOT_TOKEN),
        "message": "Telegram is running via polling" if status.get("running") else "Telegram is not active"
    }


@app.post("/telegram/restart")
async def restart_telegram():
    """Reinicia el servicio de Telegram"""
    global telegram_manager

    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=400, detail="TELEGRAM_BOT_TOKEN not configured")

    try:
        if telegram_manager:
            await telegram_manager.shutdown()

        from .core.telegram_manager import TelegramManager
        telegram_manager = TelegramManager(agent)
        await telegram_manager.initialize()

        return {"message": "Telegram restarted successfully", "status": telegram_manager.get_status()}

    except Exception as e:
        logger.error(f"Error restarting Telegram: {e}")
        raise HTTPException(status_code=500, detail=f"Error restarting Telegram: {str(e)}")


@app.post("/chat", response_model=MessageResponse)
async def chat_endpoint(
        request: MessageRequest,
        agent: BotAgent = Depends(get_agent)
):
    """Endpoint principal para el chat"""
    try:
        response = await agent.process_message(
            message=request.message,
            session_id=request.session_id,
            platform=request.platform,
            user_id=request.user_id,
            system_prompt=request.system_prompt
        )

        return MessageResponse(
            response=response,
            session_id=request.session_id
        )

    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail="Error processing message")


@app.get("/session/{session_id}", response_model=SessionInfo)
async def get_session_info(
        session_id: str,
        agent: BotAgent = Depends(get_agent)
):
    """Obtiene información detallada de una sesión"""
    try:
        session_info = await agent.get_session_summary(session_id)
        return SessionInfo(**session_info)
    except Exception as e:
        logger.error(f"Error getting session info: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving session info")


@app.delete("/session/{session_id}")
async def clear_session(
        session_id: str,
        agent: BotAgent = Depends(get_agent)
):
    """Limpia una sesión específica"""
    try:
        success = await agent.clear_conversation(session_id)
        if success:
            return {"message": f"Session {session_id} cleared successfully"}
        else:
            raise HTTPException(status_code=404, detail="Session not found or already empty")
    except Exception as e:
        logger.error(f"Error clearing session: {e}")
        raise HTTPException(status_code=500, detail="Error clearing session")


@app.get("/sessions", response_model=List[str])
async def list_sessions(agent: BotAgent = Depends(get_agent)):
    """Lista todas las sesiones activas"""
    try:
        sessions = await agent.list_active_sessions()
        return sessions
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail="Error listing sessions")


@app.get("/sessions/count")
async def get_sessions_count(agent: BotAgent = Depends(get_agent)):
    """Obtiene el número de sesiones activas"""
    try:
        sessions = await agent.list_active_sessions()
        return {"active_sessions": len(sessions)}
    except Exception as e:
        logger.error(f"Error getting session count: {e}")
        raise HTTPException(status_code=500, detail="Error getting session count")


# Webhook de Telegram (para compatibilidad, aunque usamos polling)
if settings.TELEGRAM_BOT_TOKEN:
    @app.post("/webhook/telegram")
    async def telegram_webhook(request: dict):
        """Webhook para Telegram (modo compatibilidad)"""
        if telegram_manager and telegram_manager.get_adapter():
            try:
                return await telegram_manager.get_adapter().handle_webhook(request)
            except Exception as e:
                logger.error(f"Error en webhook Telegram: {e}")
                return {"status": "error", "message": "Internal server error"}
        else:
            return {"status": "telegram_not_configured"}

# Otros webhooks condicionales
if settings.WHATSAPP_ACCESS_TOKEN:
    @app.post("/webhook/whatsapp")
    async def whatsapp_webhook(
            request: dict,
            agent: BotAgent = Depends(get_agent)
    ):
        """Webhook para WhatsApp Business API"""
        try:
            from .adapters.whatsapp import WhatsAppAdapter
            adapter = WhatsAppAdapter(agent)
            return await adapter.handle_webhook(request)
        except Exception as e:
            logger.error(f"Error en webhook WhatsApp: {e}")
            return {"status": "error", "message": "Internal server error"}

if settings.DISCORD_BOT_TOKEN:
    @app.post("/webhook/discord")
    async def discord_webhook(
            request: dict,
            agent: BotAgent = Depends(get_agent)
    ):
        """Webhook para Discord interactions"""
        try:
            from .adapters.discord import DiscordAdapter
            adapter = DiscordAdapter(agent)
            return await adapter.handle_interaction(request)
        except Exception as e:
            logger.error(f"Error en webhook Discord: {e}")
            return {"type": 4, "data": {"content": "Error interno del servidor"}}

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )