# app/adapters/whatsapp_web.py
import asyncio
import logging
import re
import json
import time
import base64
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

logger = logging.getLogger(__name__)


class WhatsAppWebAdapter:
    def __init__(self, agent):
        self.agent = agent
        self.driver = None
        self.running = False
        self.polling_task = None
        self.processed_messages = set()
        self.last_check_time = datetime.now()
        
        # Selectores CSS para WhatsApp Web (actualizados para 2025)
        self.selectors = {
            "qr_code": "canvas[aria-label='Scan me!'], div[data-testid='qr-code']",
            "search_box": "div[contenteditable='true'][data-tab='3']",
            "chat_list": "div[data-testid='chat-list'], #side div[role='grid']",
            "chat_item": "div[data-testid='cell-frame-container'], div[role='listitem']",
            "message_input": "div[contenteditable='true'][data-tab='10'], div[data-testid='conversation-compose-box-input']",
            "send_button": "button[data-testid='compose-btn-send'], span[data-testid='send']",
            "messages_container": "div[data-testid='conversation-panel-messages'], div[role='application']",
            "message_bubble": "div[data-testid='msg-container'], div[class*='message']",
            "message_text": "span[data-testid='msg-text'], span[class*='copyable-text']",
            "sender_name": "span[data-testid='msg-meta-sender'], span[class*='quoted-mention']",
            "reply_indicator": "div[data-testid='quoted-msg'], div[class*='quoted-mention']",
            "chat_header": "header[data-testid='conversation-header'], div[data-testid='conversation-info-header']",
            "group_participants": "span[data-testid='chat-subtitle'], div[class*='chat-subtitle']",
            "unread_count": "span[data-testid='icon-unread-count'], div[class*='unread']"
        }

    async def _setup_driver(self):
        """Configura el driver de Selenium para funcionar headless"""
        try:
            chrome_options = Options()
            
            # Configuraciones para servidor/headless
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-web-security")
            chrome_options.add_argument("--disable-features=VizDisplayCompositor")
            
            # User agent para parecer navegador real
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            # Ocultar automatización
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Persistir sesión (directorio de perfil personalizado)
            chrome_options.add_argument("--user-data-dir=./whatsapp_chrome_profile")
            chrome_options.add_argument("--profile-directory=MeshChileBot")
            
            # Configuraciones adicionales para estabilidad
            chrome_options.add_argument("--disable-background-timer-throttling")
            chrome_options.add_argument("--disable-backgrounding-occluded-windows")
            chrome_options.add_argument("--disable-renderer-backgrounding")
            
            self.driver = webdriver.Chrome(options=chrome_options)
            
            # Ocultar indicadores de webdriver
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info("✅ Driver de Chrome configurado exitosamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error configurando driver: {e}")
            logger.error("💡 Asegúrate de tener Chrome y chromedriver instalados")
            return False

    async def _wait_for_whatsapp_load(self):
        """Espera a que WhatsApp Web cargue y maneja autenticación"""
        try:
            logger.info("🌐 Navegando a WhatsApp Web...")
            self.driver.get("https://web.whatsapp.com")
            
            # Esperar hasta 30 segundos por el QR code o la carga completa
            wait = WebDriverWait(self.driver, 30)
            
            try:
                # Verificar si hay QR code (primera vez o sesión expirada)
                qr_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, self.selectors["qr_code"])))
                logger.info("📱 QR CODE DETECTADO - Necesaria autenticación")
                
                # Intentar mostrar QR en terminal
                await self._show_qr_in_terminal()
                
                # Esperar hasta que desaparezca el QR (usuario se autenticó)
                logger.info("⏳ Esperando autenticación... (máximo 5 minutos)")
                wait_auth = WebDriverWait(self.driver, 300)
                wait_auth.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, self.selectors["qr_code"])))
                logger.info("✅ Autenticación completada!")
                
            except TimeoutException:
                # Si no hay QR, probablemente ya está autenticado
                logger.info("✅ WhatsApp Web ya autenticado (sesión guardada)")
            
            # Esperar a que cargue la lista de chats
            logger.info("⏳ Esperando que cargue la interfaz...")
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, self.selectors["chat_list"])))
            logger.info("✅ WhatsApp Web cargado completamente")
            
            # Esperar un poco más para asegurar carga completa
            await asyncio.sleep(5)
            return True
            
        except TimeoutException:
            logger.error("❌ Timeout esperando que cargue WhatsApp Web")
            logger.error("💡 Verifica tu conexión a internet y que WhatsApp Web esté disponible")
            return False
        except Exception as e:
            logger.error(f"❌ Error cargando WhatsApp Web: {e}")
            return False

    async def _show_qr_in_terminal(self):
        """Intenta mostrar el QR code en terminal (si es posible)"""
        try:
            # Esperar un poco a que el QR se genere completamente
            await asyncio.sleep(3)
            
            # Obtener el canvas del QR
            qr_canvas = self.driver.find_element(By.CSS_SELECTOR, self.selectors["qr_code"])
            
            # Ejecutar JavaScript para obtener el QR como imagen
            qr_data_url = self.driver.execute_script("""
                var canvas = arguments[0];
                return canvas.toDataURL('image/png');
            """, qr_canvas)
            
            if qr_data_url:
                logger.info("📱 QR CODE DISPONIBLE:")
                logger.info("🔗 Abre WhatsApp en tu móvil > Menú > Dispositivos vinculados > Vincular dispositivo")
                logger.info("📷 Escanea el QR que aparece en WhatsApp Web")
                logger.info("💾 La sesión se guardará para futuros usos")
                
                # Intentar mostrar QR como ASCII (opcional)
                try:
                    await self._display_qr_as_ascii(qr_data_url)
                except:
                    pass
                    
        except Exception as e:
            logger.warning(f"No se pudo extraer QR para mostrar: {e}")
            logger.info("📱 Abre https://web.whatsapp.com en tu navegador y escanea el QR")

    async def _display_qr_as_ascii(self, qr_data_url: str):
        """Convierte QR a ASCII para mostrar en terminal (opcional)"""
        try:
            # Esta es una implementación básica
            # Podrías usar librerías como 'qrcode' para mejor resultado
            logger.info("🔲 QR CODE (abre WhatsApp Web en navegador si no se ve bien):")
            logger.info("=" * 50)
            logger.info("█████████████████████████████████████████████████")
            logger.info("█   ▄▄▄▄▄   █▀ ▄▄█▄▄▄  ▀█   ▄▄▄▄▄   ██▄▄▄  ▀█")
            logger.info("█   █   █   █▀▀▀▀██▀▀▀▀▀█   █   █   ██▀▀▀▀▀▀█")
            logger.info("█   █▄▄▄█   █▄█ █▄▄▄▄ ▄█   █▄▄▄█   ██▄▄▄▄▄▄█")
            logger.info("█▄▄▄▄▄▄▄▄▄▄▄█▀█ █▀█ █▀█▄▄▄▄▄▄▄▄▄▄▄█▀█ █▀█ █▀█")
            logger.info("█████████████████████████████████████████████████")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.debug(f"No se pudo mostrar QR como ASCII: {e}")

    def _is_bot_mentioned(self, message_text: str, chat_type: str = "group") -> bool:
        """Verifica si el bot fue mencionado en grupos"""
        if not message_text or chat_type != "group":
            return False
            
        text_lower = message_text.lower().strip()
        
        mention_patterns = [
            r'@bot\b',
            r'@asistente\b',
            r'@meshchile\b',
            r'^bot[,:\s]',
            r'^asistente[,:\s]',
            r'^hey bot\b',
            r'^hola bot\b',
            r'\bbot\b.*\?'
        ]
        
        for pattern in mention_patterns:
            if re.search(pattern, text_lower):
                logger.info(f"🏷️ Detectada mención por patrón: {pattern}")
                return True
                
        return False

    def _is_reply_to_bot(self, message_element) -> Tuple[bool, str]:
        """Verifica si es respuesta a un mensaje del bot y extrae contexto"""
        try:
            reply_element = message_element.find_element(By.CSS_SELECTOR, self.selectors["reply_indicator"])
            
            if reply_element:
                quoted_text = reply_element.text.strip()
                
                # Verificar si el mensaje citado parece ser del bot
                bot_indicators = [
                    "MeshChile", "Meshtastic", "🔗", "📡", "🇨🇱",
                    "configuración", "nodos", "red mesh"
                ]
                
                text_lower = quoted_text.lower()
                for indicator in bot_indicators:
                    if indicator.lower() in text_lower:
                        logger.info("💬 Detectada respuesta al bot")
                        return True, quoted_text[:100]
                        
                # Si el mensaje citado es muy largo, probablemente es del bot
                if len(quoted_text) > 100:
                    return True, quoted_text[:100]
                    
        except NoSuchElementException:
            pass
            
        return False, ""

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
        """Sanitiza el mensaje para WhatsApp Web"""
        if not text:
            return "Mensaje vacío"
            
        if len(text) > 4000:
            text = text[:3950] + "\n\n... (mensaje truncado por longitud)"
            
        # Limpiar caracteres problemáticos
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        text = re.sub(r'\n{4,}', '\n\n\n', text)
        
        return text

    def _get_session_id(self, chat_name: str, chat_type: str, sender_name: str = None) -> str:
        """Genera session ID apropiado"""
        if chat_type == "private":
            return f"whatsapp_web_private_{chat_name}_{sender_name or 'unknown'}"
        else:
            return f"whatsapp_web_group_{chat_name}"

    async def _get_new_messages(self) -> List[Dict]:
        """Obtiene mensajes nuevos mediante polling de chats con notificación"""
        new_messages = []
        
        try:
            # Buscar chats con mensajes no leídos
            unread_chats = self.driver.find_elements(By.CSS_SELECTOR, 
                f"{self.selectors['chat_item']}:has({self.selectors['unread_count']})")
            
            # Si no hay chats con indicador de no leído, revisar los primeros chats
            if not unread_chats:
                # Obtener primeros 5 chats (pueden tener mensajes nuevos sin indicador)
                all_chats = self.driver.find_elements(By.CSS_SELECTOR, self.selectors["chat_item"])
                unread_chats = all_chats[:5] if all_chats else []
            
            for chat_element in unread_chats:
                try:
                    # Hacer clic en el chat para abrirlo
                    chat_element.click()
                    await asyncio.sleep(2)  # Esperar a que cargue
                    
                    # Obtener info del chat actual
                    chat_info = await self._get_current_chat_info()
                    
                    if not chat_info:
                        continue
                        
                    # Obtener mensajes recientes de este chat
                    messages = await self._get_recent_messages_from_current_chat(chat_info)
                    new_messages.extend(messages)
                    
                except Exception as e:
                    logger.error(f"Error procesando chat: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error obteniendo mensajes nuevos: {e}")
            
        return new_messages

    async def _get_current_chat_info(self) -> Optional[Dict]:
        """Obtiene información del chat actual"""
        try:
            header = self.driver.find_element(By.CSS_SELECTOR, self.selectors["chat_header"])
            
            # Nombre del chat (primer span con title o texto visible)
            chat_name_elements = header.find_elements(By.CSS_SELECTOR, "span[title], span")
            chat_name = "Chat desconocido"
            
            for element in chat_name_elements:
                title = element.get_attribute("title")
                text = element.text.strip()
                if title and len(title) > 2:
                    chat_name = title
                    break
                elif text and len(text) > 2 and not text.isdigit():
                    chat_name = text
                    break
            
            # Determinar si es grupo buscando indicadores
            try:
                participants_element = header.find_element(By.CSS_SELECTOR, self.selectors["group_participants"])
                participants_text = participants_element.text
                
                # Si contiene "participantes" o números, es un grupo
                if "participante" in participants_text.lower() or re.search(r'\d+', participants_text):
                    chat_type = "group"
                else:
                    chat_type = "private"
                    
            except NoSuchElementException:
                # Sin info de participantes = probablemente chat privado
                chat_type = "private"
                participants_text = ""
                
            return {
                "name": chat_name,
                "type": chat_type,
                "participants": participants_text
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo info del chat: {e}")
            return None

    async def _get_recent_messages_from_current_chat(self, chat_info: Dict) -> List[Dict]:
        """Obtiene mensajes recientes del chat actual"""
        messages = []
        
        try:
            messages_container = self.driver.find_element(By.CSS_SELECTOR, self.selectors["messages_container"])
            
            # Obtener elementos de mensaje
            message_elements = messages_container.find_elements(By.CSS_SELECTOR, self.selectors["message_bubble"])
            
            # Revisar últimos 10 mensajes
            recent_messages = message_elements[-10:] if len(message_elements) > 10 else message_elements
            
            for msg_element in recent_messages:
                try:
                    message_data = await self._extract_message_data(msg_element, chat_info)
                    if message_data and self._is_new_message(message_data):
                        messages.append(message_data)
                        
                except Exception as e:
                    logger.debug(f"Error extrayendo mensaje: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error obteniendo mensajes del chat: {e}")
            
        return messages

    async def _extract_message_data(self, message_element, chat_info: Dict) -> Optional[Dict]:
        """Extrae datos de un elemento de mensaje"""
        try:
            # Verificar que no sea mensaje enviado por nosotros
            element_classes = message_element.get_attribute("class") or ""
            if "message-out" in element_classes or "msg-outgoing" in element_classes:
                return None
                
            # Extraer texto del mensaje
            try:
                text_elements = message_element.find_elements(By.CSS_SELECTOR, self.selectors["message_text"])
                message_text = ""
                
                for text_el in text_elements:
                    text = text_el.text.strip()
                    if text:
                        message_text = text
                        break
                        
                if not message_text:
                    return None  # Mensaje sin texto
                    
            except NoSuchElementException:
                return None
                
            # Extraer sender (solo en grupos)
            sender_name = "Usuario"
            if chat_info["type"] == "group":
                try:
                    sender_elements = message_element.find_elements(By.CSS_SELECTOR, 
                        "span[data-testid='msg-meta-sender'], span[class*='quoted-mention'], div[class*='message-author']")
                    
                    for sender_el in sender_elements:
                        name = sender_el.text.strip()
                        if name and name not in ["", "~"]:
                            sender_name = name
                            break
                            
                except NoSuchElementException:
                    pass
                    
            # Verificar si es respuesta y extraer contexto
            is_reply, reply_context = self._is_reply_to_bot(message_element)
            
            # Generar ID único del mensaje
            timestamp = str(int(time.time() * 1000))
            message_id = f"{chat_info['name']}_{sender_name}_{hash(message_text)}_{timestamp}"
            
            return {
                "id": message_id,
                "text": message_text,
                "sender": sender_name,
                "chat_name": chat_info["name"],
                "chat_type": chat_info["type"],
                "is_reply_to_bot": is_reply,
                "reply_context": reply_context,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.debug(f"Error extrayendo datos del mensaje: {e}")
            return None

    def _is_new_message(self, message_data: Dict) -> bool:
        """Verifica si el mensaje es nuevo"""
        message_id = message_data["id"]
        
        if message_id in self.processed_messages:
            return False
            
        self.processed_messages.add(message_id)
        
        # Mantener set de tamaño razonable
        if len(self.processed_messages) > 1000:
            oldest_messages = list(self.processed_messages)[:200]
            for old_id in oldest_messages:
                self.processed_messages.discard(old_id)
                
        return True

    async def _process_message(self, message_data: Dict):
        """Procesa un mensaje individual"""
        try:
            chat_type = message_data["chat_type"]
            chat_name = message_data["chat_name"]
            sender_name = message_data["sender"]
            message_text = message_data["text"]
            is_reply = message_data["is_reply_to_bot"]
            
            logger.info(f"📨 WhatsApp Web ({chat_type}: {chat_name}) - {sender_name}: {message_text[:50]}...")
            
            if chat_type == "private":
                await self._handle_private_message(message_data)
            elif chat_type == "group":
                await self._handle_group_message(message_data)
                
        except Exception as e:
            logger.error(f"❌ Error procesando mensaje: {e}")

    async def _handle_private_message(self, message_data: Dict):
        """Maneja mensajes privados"""
        chat_name = message_data["chat_name"]
        sender_name = message_data["sender"]
        message_text = message_data["text"]
        
        # Comandos especiales
        if message_text.lower() in ["hola", "start", "ayuda", "help"]:
            welcome = f"¡Hola {sender_name}! 👋\n\n🔗 Soy el asistente FAQ de la comunidad **MeshChile Meshtastic**.\n\nPuedes preguntarme sobre:\n• Configuración de nodos\n• Integraciones disponibles\n• Funciones de la comunidad\n• Soporte técnico\n\nSolo escríbeme tu pregunta normalmente."
            await self._send_message_to_chat(chat_name, welcome)
            return
            
        # Procesar con el agente
        await self._process_with_agent(message_data, "private")

    async def _handle_group_message(self, message_data: Dict):
        """Maneja mensajes de grupos"""
        message_text = message_data["text"]
        is_reply = message_data["is_reply_to_bot"]
        sender_name = message_data["sender"]
        chat_name = message_data["chat_name"]
        
        # Verificar si el bot fue mencionado O si es respuesta al bot
        is_mentioned = self._is_bot_mentioned(message_text, "group")
        
        if not is_mentioned and not is_reply:
            return
            
        interaction_type = "mención" if is_mentioned else "respuesta"
        logger.info(f"🏷️ Bot activado por {interaction_type} en grupo '{chat_name}' por {sender_name}")
        
        # Limpiar menciones del texto
        clean_text = self._clean_mention_from_text(message_text).strip()
        
        # Comandos especiales en grupos
        if clean_text.lower() in ["start", "hola", "ayuda", "help"]:
            welcome = f"¡Hola {sender_name}! 👋\n\n🔗 Soy el bot FAQ de **MeshChile Meshtastic**.\n\n📱 **En grupos**: Mencioname con @bot o responde a mis mensajes\n\n💬 **Chat privado**: Escríbeme directo\n\n🤖 Pregúntame sobre configuración, integraciones, cobertura, etc."
            await self._send_message_to_chat(chat_name, welcome)
            return
            
        if not clean_text:
            await self._send_message_to_chat(chat_name, f"{sender_name}, ¿en qué puedo ayudarte con Meshtastic? 🔗")
            return
            
        # Actualizar texto limpio
        message_data["text"] = clean_text
        await self._process_with_agent(message_data, "group")

    async def _process_with_agent(self, message_data: Dict, chat_type: str):
        """Procesa el mensaje con el agente"""
        try:
            chat_name = message_data["chat_name"]
            sender_name = message_data["sender"]
            message_text = message_data["text"]
            reply_context = message_data.get("reply_context", "")
            
            # Generar session ID
            session_id = self._get_session_id(chat_name, chat_type, sender_name)
            
            # Agregar contexto de respuesta si aplica
            if reply_context:
                message_text = f"[Respondiendo a: {reply_context}]\n\n{message_text}"
            
            # Procesar con el agente
            response = await self.agent.process_message(
                message=message_text,
                session_id=session_id,
                platform=f"whatsapp_web_{chat_type}",
                user_id=f"{chat_name}_{sender_name}"
            )
            
            # En grupos, mencionar al usuario
            if chat_type == "group":
                response = f"{sender_name}, {response}"
                
            # Sanitizar respuesta
            response = self._sanitize_message(response)
            
            # Enviar respuesta
            await self._send_message_to_chat(chat_name, response)
            logger.info(f"✅ Respuesta enviada a {sender_name} en {chat_type}")
            
        except Exception as e:
            logger.error(f"❌ Error procesando con agente: {e}")
            error_response = "Disculpa, tuve un problema procesando tu pregunta. ¿Puedes intentar de nuevo?"
            
            if chat_type == "group":
                error_response = f"{sender_name}, {error_response}"
                
            await self._send_message_to_chat(chat_name, error_response)

    async def _send_message_to_chat(self, chat_name: str, message: str):
        """Envía un mensaje a un chat específico"""
        try:
            # Buscar y abrir el chat
            if not await self._open_chat(chat_name):
                logger.error(f"No se pudo abrir el chat: {chat_name}")
                return False
                
            # Escribir mensaje
            input_box = self.driver.find_element(By.CSS_SELECTOR, self.selectors["message_input"])
            input_box.click()
            input_box.clear()
            
            # Enviar texto línea por línea para manejar saltos de línea
            lines = message.split('\n')
            for i, line in enumerate(lines):
                input_box.send_keys(line)
                if i < len(lines) - 1:
                    input_box.send_keys(Keys.SHIFT + Keys.ENTER)
            
            # Enviar mensaje
            send_button = self.driver.find_element(By.CSS_SELECTOR, self.selectors["send_button"])
            send_button.click()
            
            await asyncio.sleep(2)  # Esperar a que se envíe
            return True
            
        except Exception as e:
            logger.error(f"Error enviando mensaje a {chat_name}: {e}")
            return False

    async def _open_chat(self, chat_name: str) -> bool:
        """Abre un chat específico buscándolo"""
        try:
            # Buscar el chat
            search_box = self.driver.find_element(By.CSS_SELECTOR, self.selectors["search_box"])
            search_box.click()
            search_box.clear()
            search_box.send_keys(chat_name)
            
            await asyncio.sleep(3)  # Esperar resultados de búsqueda
            
            # Hacer clic en el primer resultado
            first_chat = self.driver.find_element(By.CSS_SELECTOR, self.selectors["chat_item"])
            first_chat.click()
            
            await asyncio.sleep(2)  # Esperar a que abra
            
            # Limpiar búsqueda presionando Escape
            search_box.send_keys(Keys.ESCAPE)
            
            return True
            
        except Exception as e:
            logger.error(f"Error abriendo chat {chat_name}: {e}")
            return False

    async def _polling_loop(self):
        """Loop principal de polling"""
        logger.info("🤖 Iniciando polling de WhatsApp Web...")
        
        while self.running:
            try:
                # Verificar que el driver sigue activo
                if not self.driver:
                    logger.error("Driver no disponible")
                    break
                    
                # Verificar que WhatsApp Web sigue cargado
                try:
                    self.driver.find_element(By.CSS_SELECTOR, self.selectors["chat_list"])
                except NoSuchElementException:
                    logger.warning("WhatsApp Web parece haber perdido conexión, reintentando...")
                    await asyncio.sleep(10)
                    continue
                    
                # Obtener mensajes nuevos
                new_messages = await self._get_new_messages()
                
                # Procesar cada mensaje
                for message in new_messages:
                    await self._process_message(message)
                    
                # Pausa entre verificaciones
                await asyncio.sleep(8)  # 8 segundos entre polls
                
            except asyncio.CancelledError:
                logger.info("📱 Polling de WhatsApp Web cancelado")
                break
            except Exception as e:
                logger.error(f"❌ Error en polling de WhatsApp Web: {e}")
                await asyncio.sleep(15)  # Pausa más larga en caso de error

    def is_enabled(self):
        """WhatsApp Web siempre está disponible (no requiere tokens)"""
        return True

    async def start_polling(self):
        """Inicia el adaptador de WhatsApp Web"""
        if self.running:
            logger.warning("⚠️ WhatsApp Web ya está ejecutándose")
            return False
            
        try:
            logger.info("🚀 Iniciando WhatsApp Web Adapter...")
            
            # Configurar driver
            if not await self._setup_driver():
                return False
                
            # Cargar WhatsApp Web y manejar autenticación
            if not await self._wait_for_whatsapp_load():
                if self.driver:
                    self.driver.quit()
                return False
                
            # Iniciar polling
            self.running = True
            self.polling_task = asyncio.create_task(self._polling_loop())
            logger.info("✅ WhatsApp Web adapter iniciado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error iniciando WhatsApp Web: {e}")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            return False

    async def stop_polling(self):
        """Detiene el adaptador"""
        logger.info("🛑 Deteniendo WhatsApp Web adapter...")
        self.running = False
        
        if self.polling_task:
            self.polling_task.cancel()
            try:
                await self.polling_task
            except asyncio.CancelledError:
                pass
            self.polling_task = None
            
        if self.driver:
            try:
                self.driver.quit()
                logger.info("✅ Driver cerrado")
            except:
                pass
            self.driver = None
            
        logger.info("🛑 WhatsApp Web adapter detenido")

    def get_status(self):
        """Estado del adaptador"""
        return {
            "enabled": True,
            "running": self.running,
            "method": "selenium_web_automation",
            "driver_active": bool(self.driver),
            "processed_messages": len(self.processed_messages),
            "supports_groups": True,
            "requires_qr": "Depends on saved session"
        }