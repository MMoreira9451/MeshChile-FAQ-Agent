# app/main.py
from fastapi import FastAPI, HTTPException, Depends, Query, Request
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
    description="Backend universal para bot multi-plataforma con Open Web UI, Redis, Telegram, WhatsApp y Discord integrados"
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
whatsapp_manager = None
discord_manager = None


@app.on_event("startup")
async def startup_event():
    """Inicialización al arrancar - incluye todas las plataformas automáticamente"""
    global agent, telegram_manager, whatsapp_manager, discord_manager
    logger.info("🚀 Iniciando Bot Agent con múltiples plataformas...")

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
            try:
                logger.info("📱 Inicializando Telegram...")
                from .core.telegram_manager import TelegramManager

                telegram_manager = TelegramManager(agent)
                await telegram_manager.initialize()
                logger.info("✅ Telegram inicializado correctamente")
            except ImportError as e:
                logger.error(f"❌ Error importando TelegramManager: {e}")
                logger.error("💡 Verifica que existe app/core/telegram_manager.py")
            except Exception as e:
                logger.error(f"❌ Error inicializando Telegram: {e}")
        else:
            logger.info("ℹ️ Telegram no configurado (TELEGRAM_BOT_TOKEN faltante)")

        # Inicializar WhatsApp automáticamente
        try:
            logger.info("💬 Inicializando WhatsApp...")
            from .core.whatsapp_manager import WhatsAppManager

            whatsapp_manager = WhatsAppManager(agent)
            await whatsapp_manager.initialize("auto")

            status = whatsapp_manager.get_status()
            if status.get("status") in ["running_api", "running_web"]:
                method = status.get("active_adapter", "unknown")
                logger.info(f"✅ WhatsApp activo via {method.upper()}")
            else:
                logger.info("ℹ️ WhatsApp no configurado o falló inicialización")

        except ImportError as e:
            logger.error(f"❌ Error importando WhatsAppManager: {e}")
            logger.error("💡 Faltan archivos de WhatsApp:")
            logger.error("   - app/core/whatsapp_manager.py")
            logger.error("   - app/adapters/whatsapp_api.py")
            logger.error("   - app/adapters/whatsapp_web.py")
        except Exception as e:
            logger.error(f"❌ Error inicializando WhatsApp: {e}")

        # Inicializar Discord automáticamente
        if settings.DISCORD_BOT_TOKEN:
            try:
                logger.info("🎮 Inicializando Discord...")
                from .core.discord_manager import DiscordManager

                discord_manager = DiscordManager(agent)
                await discord_manager.initialize()

                status = discord_manager.get_status()
                if status.get("status") == "running":
                    logger.info("✅ Discord inicializado correctamente")
                else:
                    logger.info("ℹ️ Discord configurado pero falló inicialización")

            except ImportError as e:
                logger.error(f"❌ Error importando DiscordManager: {e}")
                logger.error("💡 Faltan archivos de Discord:")
                logger.error("   - app/core/discord_manager.py")
                logger.error("   - app/adapters/discord.py")
            except Exception as e:
                logger.error(f"❌ Error inicializando Discord: {e}")
        else:
            logger.info("ℹ️ Discord no configurado (DISCORD_BOT_TOKEN faltante)")

        # Verificar conectividad general
        health = await agent.health_check()
        if health["status"] != "healthy":
            logger.warning(f"⚠️ Algunos componentes no están saludables: {health}")
        else:
            logger.info("✅ Todos los componentes están saludables")

        print("\n🎉 ¡Bot Agent listo!")

        # Estado de Telegram
        if telegram_manager and telegram_manager.get_status().get("status") == "running":
            print("📱 Telegram: ✅ Activo y funcionando")
            print("💡 Busca tu bot en Telegram y empieza a chatear")
        else:
            print("📱 Telegram: ⚠️ No configurado o falló")

        # Estado de WhatsApp
        if whatsapp_manager:
            status = whatsapp_manager.get_status()
            if status.get("status") in ["running_api", "running_web"]:
                method = status.get("active_adapter", "unknown")
                print(f"💬 WhatsApp: ✅ Activo via {method.upper()}")
                if method == "web":
                    print("💡 Si es primera vez, escanea el QR que aparece arriba")
            else:
                print("💬 WhatsApp: ⚠️ No configurado o falló")
        else:
            print("💬 WhatsApp: ⚠️ No inicializado (archivos faltantes)")

        # Estado de Discord
        if discord_manager and discord_manager.get_status().get("status") == "running":
            print("🎮 Discord: ✅ Activo y funcionando")
            guild_config = f" en servidor {settings.DISCORD_GUILD_ID}" if settings.DISCORD_GUILD_ID else " en todos los servidores"
            channel_config = f" canal {settings.DISCORD_CHANNEL_ID}" if settings.DISCORD_CHANNEL_ID else " cualquier canal"
            print(f"💡 Configurado para{guild_config},{channel_config}")
        else:
            print("🎮 Discord: ⚠️ No configurado o falló")

        print()

    except Exception as e:
        logger.error(f"❌ Error inicializando Bot Agent: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Limpieza al cerrar - incluye todas las plataformas"""
    global telegram_manager, whatsapp_manager, discord_manager
    logger.info("👋 Cerrando Bot Agent...")

    # Cerrar Telegram si está activo
    if telegram_manager:
        try:
            await telegram_manager.shutdown()
        except Exception as e:
            logger.error(f"Error cerrando Telegram: {e}")

    # Cerrar WhatsApp si está activo
    if whatsapp_manager:
        try:
            await whatsapp_manager.shutdown()
        except Exception as e:
            logger.error(f"Error cerrando WhatsApp: {e}")

    # Cerrar Discord si está activo
    if discord_manager:
        try:
            await discord_manager.shutdown()
        except Exception as e:
            logger.error(f"Error cerrando Discord: {e}")


def get_agent() -> BotAgent:
    """Dependency para obtener la instancia del agente"""
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent


@app.get("/")
async def root():
    """Endpoint raíz con información del servicio"""
    telegram_status = "disabled"
    whatsapp_status = "disabled"
    discord_status = "disabled"

    if telegram_manager:
        try:
            status = telegram_manager.get_status()
            telegram_status = status.get("status", "unknown")
        except Exception:
            telegram_status = "error"

    # Estado de WhatsApp
    if whatsapp_manager:
        try:
            status = whatsapp_manager.get_status()
            whatsapp_status = status.get("status", "unknown")
        except Exception:
            whatsapp_status = "error"

    # Estado de Discord
    if discord_manager:
        try:
            status = discord_manager.get_status()
            discord_status = status.get("status", "unknown")
        except Exception:
            discord_status = "error"

    platforms_enabled = {
        "telegram": {
            "configured": bool(settings.TELEGRAM_BOT_TOKEN),
            "status": telegram_status,
            "method": "polling" if settings.TELEGRAM_BOT_TOKEN else "none"
        },
        "whatsapp": {
            "configured": True,  # WhatsApp siempre está "disponible"
            "status": whatsapp_status,
            "method": whatsapp_manager.preferred_method if whatsapp_manager else "none"
        },
        "discord": {
            "configured": bool(settings.DISCORD_BOT_TOKEN),
            "status": discord_status,
            "method": "gateway" if settings.DISCORD_BOT_TOKEN else "none",
            "guild_id": settings.DISCORD_GUILD_ID,
            "channel_id": settings.DISCORD_CHANNEL_ID
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
            "telegram_status": "/telegram/status",
            "whatsapp_status": "/whatsapp/status",
            "discord_status": "/discord/status"
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health_check(agent: BotAgent = Depends(get_agent)):
    """Health check completo del sistema incluyendo todas las plataformas"""
    try:
        health = await agent.health_check()

        # Añadir estado de Telegram
        if telegram_manager:
            try:
                telegram_status = telegram_manager.get_status()
                health["components"]["telegram"] = {
                    "status": "healthy" if telegram_status.get("status") == "running" else "inactive",
                    "enabled": telegram_status.get("enabled", False),
                    "running": telegram_status.get("running", False)
                }
            except Exception as e:
                health["components"]["telegram"] = {
                    "status": "error",
                    "enabled": False,
                    "running": False,
                    "error": str(e)
                }
        else:
            health["components"]["telegram"] = {
                "status": "disabled",
                "enabled": False,
                "running": False
            }

        # Añadir estado de WhatsApp
        if whatsapp_manager:
            try:
                whatsapp_status = whatsapp_manager.get_status()
                health["components"]["whatsapp"] = {
                    "status": "healthy" if whatsapp_status.get("status") in ["running_api",
                                                                             "running_web"] else "inactive",
                    "enabled": True,
                    "method": whatsapp_status.get("active_adapter", "none"),
                    "running": whatsapp_status.get("status") != "inactive"
                }
            except Exception as e:
                health["components"]["whatsapp"] = {
                    "status": "error",
                    "enabled": False,
                    "running": False,
                    "error": str(e)
                }
        else:
            health["components"]["whatsapp"] = {
                "status": "disabled",
                "enabled": False,
                "running": False,
                "missing_files": [
                    "app/core/whatsapp_manager.py",
                    "app/adapters/whatsapp_api.py",
                    "app/adapters/whatsapp_web.py"
                ]
            }

        # Añadir estado de Discord
        if discord_manager:
            try:
                discord_status = discord_manager.get_status()
                health["components"]["discord"] = {
                    "status": "healthy" if discord_status.get("status") == "running" else "inactive",
                    "enabled": discord_status.get("enabled", False),
                    "running": discord_status.get("running", False),
                    "guild_id": discord_status.get("guild_id"),
                    "channel_id": discord_status.get("channel_id")
                }
            except Exception as e:
                health["components"]["discord"] = {
                    "status": "error",
                    "enabled": False,
                    "running": False,
                    "error": str(e)
                }
        else:
            health["components"]["discord"] = {
                "status": "disabled",
                "enabled": False,
                "running": False,
                "missing_files": [
                    "app/core/discord_manager.py",
                    "app/adapters/discord.py"
                ]
            }

        # El sistema está saludable si los componentes core están bien
        # Las plataformas son opcionales
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

    try:
        status = telegram_manager.get_status()
        return {
            "telegram": status,
            "token_configured": bool(settings.TELEGRAM_BOT_TOKEN),
            "message": "Telegram is running via polling" if status.get("running") else "Telegram is not active"
        }
    except Exception as e:
        return {
            "status": "error",
            "enabled": False,
            "message": f"Error getting Telegram status: {str(e)}"
        }


# Endpoints de WhatsApp
@app.get("/whatsapp/status")
async def get_whatsapp_status():
    """Estado específico de WhatsApp"""
    if not whatsapp_manager:
        return {
            "status": "not_initialized",
            "message": "WhatsApp manager not initialized - missing required files",
            "missing_files": [
                "app/core/whatsapp_manager.py",
                "app/adapters/whatsapp_api.py",
                "app/adapters/whatsapp_web.py"
            ]
        }

    try:
        status = whatsapp_manager.get_status()
        return {
            "whatsapp": status,
            "message": f"WhatsApp running via {status.get('active_adapter', 'none')}" if status.get(
                'status') != 'inactive' else "WhatsApp not active"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error getting WhatsApp status: {str(e)}"
        }


# Endpoints de Discord
@app.get("/discord/status")
async def get_discord_status():
    """Estado específico de Discord"""
    if not discord_manager:
        return {
            "status": "not_initialized",
            "message": "Discord manager not initialized - missing required files",
            "missing_files": [
                "app/core/discord_manager.py",
                "app/adapters/discord.py"
            ]
        }

    try:
        status = discord_manager.get_status()
        return {
            "discord": status,
            "token_configured": bool(settings.DISCORD_BOT_TOKEN),
            "guild_configured": bool(settings.DISCORD_GUILD_ID),
            "channel_configured": bool(settings.DISCORD_CHANNEL_ID),
            "message": "Discord is running via Gateway" if status.get("running") else "Discord is not active"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error getting Discord status: {str(e)}"
        }


@app.post("/whatsapp/restart")
async def restart_whatsapp():
    """Reinicia el servicio de WhatsApp"""
    global whatsapp_manager

    try:
        if not whatsapp_manager:
            from .core.whatsapp_manager import WhatsAppManager
            whatsapp_manager = WhatsAppManager(agent)

        status = await whatsapp_manager.restart()
        return {
            "message": "WhatsApp restarted successfully",
            "status": status
        }

    except ImportError as e:
        raise HTTPException(
            status_code=400,
            detail=f"WhatsApp files missing: {str(e)}. Create the required WhatsApp adapter files first."
        )
    except Exception as e:
        logger.error(f"Error restarting WhatsApp: {e}")
        raise HTTPException(status_code=500, detail=f"Error restarting WhatsApp: {str(e)}")


@app.post("/whatsapp/switch-method")
async def switch_whatsapp_method(request: dict):
    """Cambia entre método API y Web"""
    if not whatsapp_manager:
        raise HTTPException(status_code=400, detail="WhatsApp manager not initialized")

    method = request.get("method", "auto")

    if method not in ["api", "web", "auto"]:
        raise HTTPException(status_code=400, detail="Method must be 'api', 'web', or 'auto'")

    try:
        status = await whatsapp_manager.restart(method)
        return {
            "message": f"WhatsApp switched to method: {method}",
            "status": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error switching method: {str(e)}")


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


@app.post("/discord/restart")
async def restart_discord():
    """Reinicia el servicio de Discord"""
    global discord_manager

    if not settings.DISCORD_BOT_TOKEN:
        raise HTTPException(status_code=400, detail="DISCORD_BOT_TOKEN not configured")

    try:
        if discord_manager:
            await discord_manager.shutdown()

        from .core.discord_manager import DiscordManager
        discord_manager = DiscordManager(agent)
        await discord_manager.initialize()

        return {"message": "Discord restarted successfully", "status": discord_manager.get_status()}

    except Exception as e:
        logger.error(f"Error restarting Discord: {e}")
        raise HTTPException(status_code=500, detail=f"Error restarting Discord: {str(e)}")


@app.post("/discord/test-message")
async def discord_test_message(request: dict):
    """Envía un mensaje de prueba a Discord"""
    if not discord_manager:
        raise HTTPException(status_code=400, detail="Discord manager not initialized")

    channel_id = request.get("channel_id")
    message = request.get("message", "Test desde MeshChile Bot")

    if not channel_id:
        raise HTTPException(status_code=400, detail="channel_id is required")

    try:
        result = await discord_manager.send_test_message(int(channel_id), message)
        return result
    except ValueError:
        raise HTTPException(status_code=400, detail="channel_id must be a valid integer")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending test message: {str(e)}")


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


# Webhook de WhatsApp
@app.get("/webhook/whatsapp")
async def whatsapp_webhook_verify(
        request: Request,
        hub_mode: str = Query(None, alias="hub.mode"),
        hub_challenge: str = Query(None, alias="hub.challenge"),
        hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    """Verificación de webhook de WhatsApp (GET)"""
    logger.info(f"Webhook verification request: mode={hub_mode}, token={hub_verify_token}")

    # Verificar que sea una petición de suscripción válida
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("✅ Webhook verificado exitosamente")
        return int(hub_challenge) if hub_challenge and hub_challenge.isdigit() else hub_challenge
    else:
        logger.error(
            f"❌ Token de verificación inválido: esperado={settings.WHATSAPP_VERIFY_TOKEN}, recibido={hub_verify_token}")
        raise HTTPException(status_code=403, detail="Invalid verify token")


@app.post("/webhook/whatsapp")
async def whatsapp_webhook_message(request: dict):
    """Webhook para mensajes de WhatsApp (POST)"""
    if whatsapp_manager and whatsapp_manager.get_active_adapter():
        try:
            return await whatsapp_manager.handle_webhook(request)
        except Exception as e:
            logger.error(f"Error en webhook WhatsApp: {e}")
            return {"status": "error", "message": "Internal server error"}
    else:
        return {
            "status": "whatsapp_not_configured",
            "message": "WhatsApp manager not initialized or no active adapter"
        }


# Webhook de Telegram
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

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )