# app/core/whatsapp_manager.py
"""
Manager para integrar ambos adaptadores de WhatsApp con el sistema principal
"""
import asyncio
import logging
from typing import Optional, Dict
from .agent import BotAgent

logger = logging.getLogger(__name__)


class WhatsAppManager:
    def __init__(self, agent: BotAgent):
        self.agent = agent
        self.api_adapter = None
        self.web_adapter = None
        self.active_adapter = None
        self.preferred_method = "auto"  # "api", "web", o "auto"
        self._initialized = False

    async def initialize(self, method: str = "auto"):
        """
        Inicializa el manager de WhatsApp
        
        Args:
            method: "api", "web", o "auto" (intentar API primero, luego Web)
        """
        if self._initialized:
            return

        try:
            logger.info("🟢 Inicializando WhatsApp Manager...")
            
            if method == "auto":
                # Intentar API primero, luego Web como fallback
                if await self._initialize_api():
                    self.active_adapter = self.api_adapter
                    self.preferred_method = "api"
                    logger.info("✅ WhatsApp integrado via Business API")
                elif await self._initialize_web():
                    self.active_adapter = self.web_adapter
                    self.preferred_method = "web" 
                    logger.info("✅ WhatsApp integrado via Web (Selenium)")
                else:
                    logger.warning("⚠️ No se pudo inicializar ningún método de WhatsApp")
                    
            elif method == "api":
                if await self._initialize_api():
                    self.active_adapter = self.api_adapter
                    self.preferred_method = "api"
                    logger.info("✅ WhatsApp Business API inicializado")
                else:
                    logger.warning("⚠️ WhatsApp Business API no pudo inicializarse")
                    
            elif method == "web":
                if await self._initialize_web():
                    self.active_adapter = self.web_adapter
                    self.preferred_method = "web"
                    logger.info("✅ WhatsApp Web inicializado")
                else:
                    logger.warning("⚠️ WhatsApp Web no pudo inicializarse")
                    
            self._initialized = True

        except Exception as e:
            logger.error(f"❌ Error inicializando WhatsApp Manager: {e}")

    async def _initialize_api(self) -> bool:
        """Inicializa el adaptador de API oficial"""
        try:
            from ..adapters.whatsapp_api import WhatsAppAPIAdapter
            
            self.api_adapter = WhatsAppAPIAdapter(self.agent)
            
            if self.api_adapter.is_enabled():
                success = await self.api_adapter.initialize()
                if success:
                    logger.info("🔗 WhatsApp Business API configurado exitosamente")
                    return True
                else:
                    logger.warning("⚠️ WhatsApp Business API habilitado pero falló inicialización")
            else:
                logger.info("ℹ️ WhatsApp Business API no configurado (tokens faltantes)")
                
        except Exception as e:
            logger.error(f"Error inicializando WhatsApp API: {e}")
            
        return False

    async def _initialize_web(self) -> bool:
        """Inicializa el adaptador de WhatsApp Web"""
        try:
            from ..adapters.whatsapp_web import WhatsAppWebAdapter
            
            self.web_adapter = WhatsAppWebAdapter(self.agent)
            
            # WhatsApp Web siempre está "habilitado" pero puede fallar al iniciar
            success = await self.web_adapter.start_polling()
            if success:
                logger.info("🌐 WhatsApp Web configurado exitosamente")
                return True
            else:
                logger.warning("⚠️ WhatsApp Web falló al iniciar")
                
        except Exception as e:
            logger.error(f"Error inicializando WhatsApp Web: {e}")
            
        return False

    async def shutdown(self):
        """Cierra el manager de WhatsApp"""
        logger.info("👋 Cerrando WhatsApp Manager...")
        
        # Cerrar adaptador API si está activo
        if self.api_adapter:
            try:
                # El adaptador API no tiene polling que cerrar
                logger.info("📱 WhatsApp API adapter cerrado")
            except Exception as e:
                logger.error(f"Error cerrando WhatsApp API: {e}")
                
        # Cerrar adaptador Web si está activo
        if self.web_adapter and self.web_adapter.running:
            try:
                await self.web_adapter.stop_polling()
                logger.info("🌐 WhatsApp Web adapter cerrado")
            except Exception as e:
                logger.error(f"Error cerrando WhatsApp Web: {e}")

    def get_status(self):
        """Obtiene el estado de WhatsApp"""
        if not self._initialized:
            return {"status": "not_initialized"}

        status = {
            "initialized": self._initialized,
            "preferred_method": self.preferred_method,
            "active_adapter": None,
            "api_adapter": None,
            "web_adapter": None
        }

        # Estado del adaptador API
        if self.api_adapter:
            status["api_adapter"] = {
                "available": True,
                "enabled": self.api_adapter.is_enabled(),
                **self.api_adapter.get_status()
            }
        else:
            status["api_adapter"] = {"available": False}

        # Estado del adaptador Web  
        if self.web_adapter:
            status["web_adapter"] = {
                "available": True,
                **self.web_adapter.get_status()
            }
        else:
            status["web_adapter"] = {"available": False}

        # Adaptador activo
        if self.active_adapter:
            if self.active_adapter == self.api_adapter:
                status["active_adapter"] = "api"
                status["status"] = "running_api"
            elif self.active_adapter == self.web_adapter:
                status["active_adapter"] = "web" 
                status["status"] = "running_web"
        else:
            status["status"] = "inactive"

        return status

    def get_active_adapter(self):
        """Obtiene el adaptador activo (para webhook si es necesario)"""
        return self.active_adapter

    async def handle_webhook(self, request: Dict):
        """Maneja webhooks (solo para API adapter)"""
        if self.active_adapter == self.api_adapter:
            return await self.api_adapter.handle_webhook(request)
        else:
            return {"status": "webhook_not_supported", "active_method": self.preferred_method}

    async def restart(self, method: str = None):
        """Reinicia el manager con un método específico"""
        logger.info("🔄 Reiniciando WhatsApp Manager...")
        
        # Cerrar adaptadores actuales
        await self.shutdown()
        
        # Resetear estado
        self._initialized = False
        self.active_adapter = None
        
        # Reinicializar
        restart_method = method or self.preferred_method
        await self.initialize(restart_method)
        
        return self.get_status()

    def requires_qr_scan(self):
        """Verifica si se requiere escanear QR (para WhatsApp Web)"""
        if self.preferred_method == "web" and self.web_adapter:
            # Esta información tendría que venir del adaptador web
            # basado en si tiene sesión guardada o no
            return True  # Por simplicidad, asumimos que puede requerir QR
        return False

    async def send_test_message(self, phone_number: str, message: str = "Test desde MeshChile Bot"):
        """Envía un mensaje de prueba (solo para testing)"""
        if not self.active_adapter:
            return {"success": False, "error": "No hay adaptador activo"}
            
        try:
            if self.active_adapter == self.api_adapter:
                success = await self.api_adapter._send_message(phone_number, message)
                return {"success": success, "method": "api"}
            elif self.active_adapter == self.web_adapter:
                success = await self.web_adapter._send_message_to_chat(phone_number, message)
                return {"success": success, "method": "web"}
        except Exception as e:
            return {"success": False, "error": str(e)}
            
        return {"success": False, "error": "Método no soportado"}