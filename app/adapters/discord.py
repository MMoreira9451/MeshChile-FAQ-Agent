# app/adapters/discord.py
import discord
from discord.ext import commands
import asyncio
import logging
import re
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class DiscordAdapter:
    def __init__(self, agent):
        self.agent = agent
        self.bot_token = None
        self.guild_id = None
        self.channel_id = None
        self.bot = None
        self.running = False
        self.bot_user_id = None

        # Importar configuración
        try:
            from app.core.config import settings
            self.bot_token = settings.DISCORD_BOT_TOKEN
            self.guild_id = settings.DISCORD_GUILD_ID
            self.channel_id = settings.DISCORD_CHANNEL_ID
        except ImportError:
            try:
                from ..core.config import settings
                self.bot_token = settings.DISCORD_BOT_TOKEN
                self.guild_id = settings.DISCORD_GUILD_ID
                self.channel_id = settings.DISCORD_CHANNEL_ID
            except ImportError:
                logger.error("No se pudo importar configuración")

    def _setup_bot(self):
        """Configura el bot de Discord"""
        # Configurar intents necesarios
        intents = discord.Intents.default()
        intents.message_content = True  # Necesario para leer contenido de mensajes
        intents.guilds = True
        intents.guild_messages = True
        intents.dm_messages = True

        # Crear bot
        self.bot = commands.Bot(
            command_prefix='!',  # Prefix para comandos (opcional)
            intents=intents,
            help_command=None  # Deshabilitar comando help por defecto
        )

        # Configurar eventos
        self._setup_events()

        logger.info("✅ Bot de Discord configurado")

    def _setup_events(self):
        """Configura los eventos del bot"""

        @self.bot.event
        async def on_ready():
            """Evento cuando el bot se conecta"""
            self.bot_user_id = self.bot.user.id
            logger.info(f"✅ Discord bot conectado: {self.bot.user} (ID: {self.bot.user.id})")

            # Mostrar información del servidor y canal si están configurados
            if self.guild_id:
                guild = self.bot.get_guild(self.guild_id)
                guild_name = guild.name if guild else "No encontrado"
                logger.info(f"🏰 Servidor configurado: {guild_name} (ID: {self.guild_id})")

                if self.channel_id:
                    channel = self.bot.get_channel(self.channel_id)
                    channel_name = channel.name if channel else "No encontrado"
                    logger.info(f"📺 Canal configurado: #{channel_name} (ID: {self.channel_id})")
            else:
                logger.info("🌐 Funcionando en todos los servidores (DISCORD_GUILD_ID no configurado)")

        @self.bot.event
        async def on_message(message):
            """Evento cuando se recibe un mensaje"""
            # Ignorar mensajes del propio bot
            if message.author.id == self.bot_user_id:
                return

            # Procesar el mensaje
            await self._process_message(message)

            # Procesar comandos también (opcional)
            await self.bot.process_commands(message)

        @self.bot.event
        async def on_error(event, *args, **kwargs):
            """Manejo de errores"""
            logger.error(f"Error en evento Discord {event}: {args}")

    def _is_target_channel(self, message) -> bool:
        """Verifica si el mensaje es del canal objetivo"""
        # Si es DM, siempre procesar
        if isinstance(message.channel, discord.DMChannel):
            return True

        # Si no hay guild_id configurado, funciona en todos los servidores
        if not self.guild_id:
            return True

        # Verificar servidor específico
        if message.guild and message.guild.id != self.guild_id:
            return False

        # Si no hay channel_id configurado, funciona en cualquier canal del servidor
        if not self.channel_id:
            return True

        # Verificar canal específico
        return message.channel.id == self.channel_id

    def _is_bot_mentioned(self, message) -> bool:
        """Verifica si el bot fue mencionado"""
        # Verificar mención directa
        if self.bot.user in message.mentions:
            return True

        # Verificar patrones de mención en el texto
        content_lower = message.content.lower().strip()

        mention_patterns = [
            r'@bot\b',
            r'@asistente\b',
            r'@meshchile\b',
            rf'@{self.bot.user.name.lower()}\b' if self.bot.user else r'@bot\b',
            r'^bot[,:\s]',
            r'^asistente[,:\s]',
            r'^hey bot\b',
            r'^hola bot\b'
        ]

        for pattern in mention_patterns:
            if re.search(pattern, content_lower):
                return True

        return False

    def _is_reply_to_bot(self, message) -> tuple:
        """Verifica si es respuesta a un mensaje del bot"""
        if message.reference:
            # Obtener mensaje original
            try:
                original_message = message.reference.resolved
                if original_message and original_message.author.id == self.bot_user_id:
                    return True, original_message.content[:100]
            except:
                pass

        return False, ""

    def _clean_mention_from_text(self, text: str) -> str:
        """Limpia las menciones del texto para procesamiento"""
        if not text:
            return text

        # Remover menciones directas de Discord
        text = re.sub(r'<@!?\d+>', '', text)

        # Remover patrones de mención
        text = re.sub(r'@bot\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'@asistente\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'@meshchile\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^bot[,:\s]+', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^asistente[,:\s]+', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^hey bot[,:\s]*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^hola bot[,:\s]*', '', text, flags=re.IGNORECASE)

        return text.strip()

    def _sanitize_message(self, text: str) -> str:
        """Sanitiza el mensaje para Discord"""
        if not text:
            return "Mensaje vacío"

        # Discord tiene límite de 2000 caracteres
        if len(text) > 1900:
            text = text[:1850] + "\n\n... (mensaje truncado por longitud)"

        # Limpiar caracteres problemáticos
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

        return text

    def _get_session_id(self, message) -> str:
        """Genera session ID apropiado según el contexto"""
        if isinstance(message.channel, discord.DMChannel):
            # Mensaje directo
            return f"discord_dm_{message.author.id}"
        else:
            # Canal de servidor
            guild_id = message.guild.id if message.guild else "unknown"
            channel_id = message.channel.id
            return f"discord_guild_{guild_id}_channel_{channel_id}"

    async def _process_message(self, message):
        """Procesa un mensaje individual"""
        try:
            # Verificar si es del canal objetivo
            if not self._is_target_channel(message):
                return

            content = message.content.strip()
            if not content:
                return  # Ignorar mensajes vacíos

            # Información del mensaje
            author_name = message.author.display_name or message.author.name
            channel_type = "DM" if isinstance(message.channel, discord.DMChannel) else "Canal"
            channel_name = getattr(message.channel, 'name', 'DM')

            logger.info(f"📨 Discord {channel_type} #{channel_name} - {author_name}: {content[:50]}...")

            # Lógica diferente según tipo de canal
            if isinstance(message.channel, discord.DMChannel):
                await self._handle_direct_message(message)
            else:
                await self._handle_guild_message(message)

        except Exception as e:
            logger.error(f"❌ Error procesando mensaje de Discord: {e}")
            try:
                await message.channel.send(
                    "Disculpa, tuve un problema procesando tu mensaje. ¿Puedes intentar de nuevo?"
                )
            except:
                pass

    async def _handle_direct_message(self, message):
        """Maneja mensajes directos"""
        author_name = message.author.display_name or message.author.name
        content = message.content.strip()

        logger.info(f"💬 Mensaje directo de {author_name}: {content[:50]}...")

        # Comandos especiales en DM
        if content.lower() in ["hola", "start", "ayuda", "help"]:
            welcome = f"¡Hola {author_name}! 👋\n\n🔗 Soy el asistente FAQ de la comunidad **MeshChile Meshtastic**.\n\nPuedes preguntarme sobre:\n• Configuración de nodos\n• Integraciones disponibles\n• Funciones de la comunidad\n• Soporte técnico\n\nSolo escríbeme tu pregunta normalmente."
            await message.channel.send(welcome)
            return

        if len(content) < 2:
            await message.channel.send("¿Tienes alguna pregunta sobre Meshtastic o la comunidad MeshChile?")
            return

        # Procesar con el agente
        await self._process_with_agent(message, "dm")

    async def _handle_guild_message(self, message):
        """Maneja mensajes en servidores/canales"""
        author_name = message.author.display_name or message.author.name
        content = message.content.strip()

        # Verificar si el bot fue mencionado O si es respuesta al bot
        is_mentioned = self._is_bot_mentioned(message)
        is_reply, reply_context = self._is_reply_to_bot(message)

        if not is_mentioned and not is_reply:
            return  # Ignorar si no fue mencionado ni es respuesta

        interaction_type = "mención" if is_mentioned else "respuesta"
        channel_name = getattr(message.channel, 'name', 'canal')
        guild_name = message.guild.name if message.guild else 'servidor'

        logger.info(f"🏷️ Bot activado por {interaction_type} en #{channel_name} ({guild_name}) por {author_name}")

        # Limpiar menciones del texto
        clean_content = self._clean_mention_from_text(content).strip()

        # Comandos especiales en canales
        if clean_content.lower() in ["start", "hola", "ayuda", "help"]:
            welcome = f"¡Hola {author_name}! 👋\n\n🔗 Soy el bot FAQ de **MeshChile Meshtastic**.\n\n📱 **En canales**: Mencióname o responde a mis mensajes\n💬 **Mensaje directo**: Escríbeme directo\n\n🤖 Pregúntame sobre configuración, integraciones, cobertura, etc."
            await message.channel.send(welcome)
            return

        if not clean_content:
            await message.channel.send(f"{author_name}, ¿en qué puedo ayudarte con Meshtastic? 🔗")
            return

        # Actualizar contenido del mensaje para procesamiento
        original_content = message.content
        message.content = clean_content

        # Procesar pregunta
        await self._process_with_agent(message, "guild", reply_context)

        # Restaurar contenido original
        message.content = original_content

    async def _process_with_agent(self, message, message_type: str, reply_context: str = ""):
        """Procesa el mensaje con el agente"""
        try:
            author_name = message.author.display_name or message.author.name
            content = message.content.strip()

            # Mostrar que está escribiendo
            async with message.channel.typing():
                # Generar session ID
                session_id = self._get_session_id(message)

                # Agregar contexto de respuesta si aplica
                if reply_context:
                    content = f"[Respondiendo a: {reply_context}]\n\n{content}"

                # Contexto adicional para el prompt
                context_info = f"Usuario: {author_name}"
                if message_type == "guild":
                    channel_name = getattr(message.channel, 'name', 'canal')
                    guild_name = message.guild.name if message.guild else 'servidor'
                    context_info += f" (en #{channel_name} - {guild_name})"

                # Procesar con el agente
                response = await self.agent.process_message(
                    message=content,
                    session_id=session_id,
                    platform=f"discord_{message_type}",
                    user_id=str(message.author.id)
                )

                # En canales, mencionar al usuario en la respuesta
                if message_type == "guild":
                    response = f"{author_name}, {response}"

                # Sanitizar mensaje antes de enviar
                response = self._sanitize_message(response)

                # Enviar respuesta
                await message.channel.send(response)

                logger.info(f"✅ Respuesta enviada a {author_name} en {message_type}")

        except Exception as e:
            logger.error(f"❌ Error procesando con agente: {e}")
            error_response = "Disculpa, tuve un problema procesando tu pregunta sobre Meshtastic. ¿Puedes intentar de nuevo?"

            if message_type == "guild":
                author_name = message.author.display_name or message.author.name
                error_response = f"{author_name}, {error_response}"

            try:
                await message.channel.send(error_response)
            except:
                pass

    def is_enabled(self):
        """Verifica si está habilitado"""
        return bool(self.bot_token)

    async def start(self):
        """Inicia el bot de Discord"""
        if not self.bot_token:
            logger.warning("⚠️ DISCORD_BOT_TOKEN no configurado - Discord deshabilitado")
            return False

        if self.running:
            logger.warning("⚠️ Bot de Discord ya está ejecutándose")
            return False

        try:
            logger.info("🚀 Iniciando bot de Discord...")

            # Configurar bot
            self._setup_bot()

            # Marcar como running antes de conectar
            self.running = True

            # Conectar (esto es bloqueante hasta que se cierre)
            await self.bot.start(self.bot_token)

        except discord.LoginFailure:
            logger.error("❌ Token de Discord inválido")
            self.running = False
            return False
        except Exception as e:
            logger.error(f"❌ Error iniciando Discord bot: {e}")
            self.running = False
            return False

        return True

    async def stop(self):
        """Detiene el bot de Discord"""
        if not self.running:
            return

        logger.info("🛑 Deteniendo bot de Discord...")
        self.running = False

        if self.bot:
            await self.bot.close()

        logger.info("✅ Bot de Discord detenido")

    def get_status(self):
        """Estado del adaptador"""
        status = {
            "enabled": self.is_enabled(),
            "running": self.running,
            "has_token": bool(self.bot_token),
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "supports_dms": True,
            "supports_mentions": True
        }

        if self.bot and self.bot.user:
            status.update({
                "bot_username": self.bot.user.name,
                "bot_id": self.bot.user.id,
                "connected_guilds": len(self.bot.guilds) if self.bot.guilds else 0
            })

        return status

    async def send_test_message(self, channel_id: int, message: str = "Test desde MeshChile Bot"):
        """Envía un mensaje de prueba (solo para testing)"""
        if not self.bot or not self.running:
            return {"success": False, "error": "Bot no está corriendo"}

        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return {"success": False, "error": "Canal no encontrado"}

            await channel.send(message)
            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}