# MeshChile Bot Agent 🔗🇨🇱

**Bot conversacional multi-plataforma especializado en soporte técnico para Meshtastic Chile**

Un asistente inteligente que proporciona soporte automatizado sobre dispositivos Meshtastic, configuración de redes mesh LoRa, hardware especializado y regulaciones chilenas de radiocomunicaciones.

## 📋 Tabla de Contenidos

- [Características](#-características)
- [Arquitectura](#-arquitectura)
- [Requisitos](#-requisitos)
- [Instalación](#-instalación)
- [Configuración](#-configuración)
- [Despliegue](#-despliegue)
- [Uso](#-uso)
- [API REST](#-api-rest)
- [Plataformas](#-plataformas)
- [Desarrollo](#-desarrollo)
- [Troubleshooting](#-troubleshooting)

## 🚀 Características

### Soporte Técnico Especializado
- **Dispositivos Meshtastic**: T-Beam, Heltec, RAK WisBlock, Station G1
- **Configuración para Chile**: Región ANZ, slot 20, regulaciones SUBTEL
- **Hardware**: Antenas, nodos solares, sistemas de energía
- **Red Mesh**: Protocolos LoRa, MQTT, canales privados
- **Desarrollo**: Bots, automatización, integraciones

### Multi-Plataforma
- **Telegram**: Bot con polling automático
- **WhatsApp**: API oficial + Web automation (Selenium)
- **Discord**: Bot con menciones y respuestas
- **API REST**: Integración directa

### Funcionalidades Avanzadas
- **Gestión de sesiones**: Persistencia con Redis
- **Context awareness**: Memoria conversacional por usuario
- **Health monitoring**: Estado de componentes en tiempo real
- **Webhooks**: Soporte para WhatsApp Business API
- **Docker**: Despliegue containerizado

## 🏗️ Arquitectura

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Telegram      │    │   WhatsApp       │    │   Discord       │
│   Bot           │    │   API/Web        │    │   Bot           │
└─────────┬───────┘    └─────────┬────────┘    └─────────┬───────┘
          │                      │                       │
          └──────────────────────┼───────────────────────┘
                                 │
                     ┌───────────▼────────────┐
                     │                        │
                     │    FastAPI Router      │
                     │                        │
                     └───────────┬────────────┘
                                 │
                     ┌───────────▼────────────┐
                     │                        │
                     │     Bot Agent          │
                     │   (Message Processor)  │
                     │                        │
                     └─────┬──────────────┬───┘
                           │              │
                 ┌─────────▼──────┐   ┌───▼──────────┐
                 │                │   │              │
                 │  Open Web UI   │   │    Redis     │
                 │   (LLM API)    │   │  (Sessions)  │
                 │                │   │              │
                 └────────────────┘   └──────────────┘
```

### Componentes Principales

- **BotAgent**: Procesador central de mensajes
- **Platform Managers**: Orquestación de Telegram, WhatsApp, Discord
- **Platform Adapters**: Implementación específica por plataforma
- **Session Manager**: Gestión de contexto conversacional
- **OpenWebUI Client**: Interfaz con el modelo de IA

## 📋 Requisitos

### Servicios Externos Requeridos
- **Open Web UI**: Motor de IA (LLM)
- **Redis**: Base de datos para sesiones

### Servicios Opcionales (por plataforma)
- **Telegram Bot Token**: Para integración con Telegram
- **WhatsApp Business API**: Tokens de Meta para WhatsApp oficial
- **Discord Bot Token**: Para integración con Discord
- **Chrome/Chromedriver**: Para WhatsApp Web automation

### Requisitos del Sistema
- Python 3.11+
- Docker y Docker Compose (recomendado)
- Chrome/Chromium (para WhatsApp Web)

## 🛠️ Instalación

### Método 1: Docker Compose (Recomendado)

```bash
# Clonar repositorio
git clone https://github.com/tu-repo/meshchile-bot-agent
cd meshchile-bot-agent

# Copiar archivo de configuración
cp .env.example .env

# Editar configuración (ver sección Configuración)
nano .env

# Iniciar servicios
docker-compose up -d --build

# Ver logs
docker-compose logs -f bot-agent
```

### Método 2: Instalación Local

```bash
# Clonar repositorio
git clone https://github.com/tu-repo/meshchile-bot-agent
cd meshchile-bot-agent

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tu configuración

# Iniciar Redis localmente
redis-server

# Ejecutar aplicación
python run.py
```

## ⚙️ Configuración

### Configuración Base (Requerida)

```bash
# Open Web UI Configuration
OPENWEBUI_BASE_URL=http://localhost:8080
OPENWEBUI_API_KEY=tu_api_key_opcional
MODEL_NAME=llama2

# Redis Configuration  
REDIS_URL=redis://localhost:6379
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
```

### Configuración de Plataformas (Opcional)

#### Telegram
```bash
TELEGRAM_BOT_TOKEN=tu_telegram_bot_token
```

**Cómo obtener:**
1. Habla con [@BotFather](https://t.me/botfather) en Telegram
2. Ejecuta `/newbot` y sigue las instrucciones
3. Copia el token proporcionado

#### WhatsApp Business API
```bash
WHATSAPP_ACCESS_TOKEN=tu_access_token
WHATSAPP_PHONE_NUMBER_ID=tu_phone_number_id
WHATSAPP_VERIFY_TOKEN=tu_verify_token
```

**Cómo obtener:**
1. Registrarse en [Meta for Developers](https://developers.facebook.com/)
2. Crear app de WhatsApp Business
3. Configurar webhook en tu dominio

#### Discord
```bash
DISCORD_BOT_TOKEN=tu_discord_bot_token
DISCORD_APPLICATION_ID=tu_application_id
DISCORD_GUILD_ID=id_servidor_opcional
DISCORD_CHANNEL_ID=id_canal_opcional
```

**Cómo obtener:**
1. Ve a [Discord Developer Portal](https://discord.com/developers/applications)
2. Crear "New Application"
3. En "Bot" section, crear bot y copiar token
4. Invitar bot a tu servidor con permisos apropiados

## 🚀 Despliegue

### Desarrollo Local
```bash
# Con auto-reload
python run.py

# Acceder a:
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
# Health: http://localhost:8000/health
```

### Producción con Docker
```bash
# Producción en background
docker-compose up -d --build

# Con interfaz de Redis (opcional)
docker-compose --profile debug up -d

# Verificar estado
docker-compose ps
docker-compose logs -f bot-agent
```

### Producción en Servidor

```bash
# Usando systemd (Linux)
sudo nano /etc/systemd/system/meshchile-bot.service

[Unit]
Description=MeshChile Bot Agent
After=network.target

[Service]
Type=exec
User=ubuntu
WorkingDirectory=/opt/meshchile-bot
Environment=PATH=/opt/meshchile-bot/venv/bin
ExecStart=/opt/meshchile-bot/venv/bin/python run.py
Restart=always

[Install]
WantedBy=multi-user.target

# Habilitar servicio
sudo systemctl enable meshchile-bot
sudo systemctl start meshchile-bot
sudo systemctl status meshchile-bot
```

## 📱 Uso

### Telegram
1. Busca tu bot en Telegram: `@tu_bot_username`
2. Inicia conversación con `/start`
3. Haz preguntas sobre Meshtastic directamente

### WhatsApp
**API Oficial:**
- Configura webhook en tu dominio
- Los usuarios pueden escribir al número configurado

**WhatsApp Web:**
- Al primer inicio, escanea QR code
- El bot detecta menciones en grupos

### Discord
- **En servidores**: Menciona el bot `@BotName` o responde a sus mensajes
- **Mensaje directo**: Escribe directamente al bot

### API REST
```bash
# Enviar mensaje
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Cómo configuro un nodo T-Beam?",
    "session_id": "usuario_123",
    "platform": "api"
  }'

# Ver estado del sistema
curl http://localhost:8000/health

# Listar sesiones activas
curl http://localhost:8000/sessions
```

## 🔌 API REST

### Endpoints Principales

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/` | Información del servicio |
| `GET` | `/health` | Estado de componentes |
| `POST` | `/chat` | Enviar mensaje |
| `GET` | `/sessions` | Listar sesiones |
| `GET` | `/session/{id}` | Info de sesión |
| `DELETE` | `/session/{id}` | Limpiar sesión |

### Endpoints de Plataformas

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/telegram/status` | Estado de Telegram |
| `POST` | `/telegram/restart` | Reiniciar Telegram |
| `GET` | `/whatsapp/status` | Estado de WhatsApp |
| `POST` | `/whatsapp/restart` | Reiniciar WhatsApp |
| `POST` | `/whatsapp/switch-method` | Cambiar API/Web |
| `GET` | `/discord/status` | Estado de Discord |
| `POST` | `/discord/restart` | Reiniciar Discord |

### Webhooks

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET/POST` | `/webhook/whatsapp` | Webhook WhatsApp |
| `POST` | `/webhook/telegram` | Webhook Telegram |

## 🎮 Plataformas

### Telegram
- **Método**: Polling automático
- **Características**: 
  - Soporte grupos y chats privados
  - Mensiones y respuestas
  - Comandos especiales
  - Threads en supergrupos

### WhatsApp  
- **Método 1 - API Oficial**: Webhooks de Meta
- **Método 2 - Web Automation**: Selenium + Chrome
- **Características**:
  - Detección automática del mejor método
  - Soporte grupos y chats privados
  - QR code para primera configuración (Web)

### Discord
- **Método**: Gateway connection
- **Características**:
  - Soporte servidores específicos
  - Canales específicos
  - Menciones y respuestas
  - Mensajes directos

## 🔧 Desarrollo

### Estructura del Proyecto
```
app/
├── core/                    # Lógica principal
│   ├── agent.py            # Procesador de mensajes
│   ├── config.py           # Configuración
│   ├── openwebui_client.py # Cliente Open Web UI
│   ├── telegram_manager.py # Manager Telegram
│   ├── whatsapp_manager.py # Manager WhatsApp
│   └── discord_manager.py  # Manager Discord
├── adapters/               # Adaptadores por plataforma
│   ├── telegram.py         # Bot Telegram
│   ├── whatsapp_api.py     # WhatsApp API oficial
│   ├── whatsapp_web.py     # WhatsApp Web automation
│   └── discord.py          # Bot Discord
├── models/                 # Modelos de datos
│   ├── message.py          # Modelos de mensajes
│   └── session.py          # Gestión de sesiones
└── main.py                 # FastAPI app principal
```

### Agregar Nueva Plataforma

1. **Crear adaptador** en `app/adapters/nueva_plataforma.py`:
```python
class NuevaPlataformaAdapter:
    def __init__(self, agent):
        self.agent = agent
    
    async def process_message(self, message_data):
        # Implementar lógica específica
        pass
```

2. **Crear manager** en `app/core/nueva_plataforma_manager.py`:
```python
class NuevaPlataformaManager:
    def __init__(self, agent):
        self.agent = agent
        self.adapter = NuevaPlataformaAdapter(agent)
    
    async def initialize(self):
        # Inicialización
        pass
```

3. **Integrar en main.py**:
```python
# En startup_event()
nueva_plataforma_manager = NuevaPlataformaManager(agent)
await nueva_plataforma_manager.initialize()
```

### Testing

```bash
# Test API REST
python scripts/test_api.py

# Test específico de componentes
python -m pytest tests/ -v

# Test manual de plataformas
# Verificar en /health y endpoints de estado
```

## 🐛 Troubleshooting

### Problemas Comunes

#### Redis no conecta
```bash
# Verificar que Redis está corriendo
redis-cli ping

# En Docker
docker-compose logs redis

# Verificar configuración
echo $REDIS_URL
```

#### Open Web UI no responde
```bash
# Verificar que Open Web UI está accesible
curl http://localhost:8080/health

# Verificar configuración
echo $OPENWEBUI_BASE_URL
```

#### WhatsApp Web no funciona
```bash
# Verificar Chrome/chromedriver
which google-chrome
which chromedriver

# Permisos de directorio de perfil
chmod -R 755 ./whatsapp_chrome_profile

# Reinstalar dependencias
pip install selenium==4.34.2
```

#### Telegram no recibe mensajes
```bash
# Verificar token
curl https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe

# Ver logs detallados
docker-compose logs -f bot-agent | grep telegram
```

#### Discord no responde
```bash
# Verificar token y permisos
# El bot debe tener permisos de:
# - Read Messages
# - Send Messages  
# - Read Message History
# - Use Slash Commands (opcional)

# Verificar que el bot está en el servidor correcto
# Si DISCORD_GUILD_ID está configurado
```

### Logs y Diagnóstico

```bash
# Ver todos los logs
docker-compose logs -f

# Logs específicos por servicio
docker-compose logs -f bot-agent
docker-compose logs -f redis

# Health check completo
curl http://localhost:8000/health | jq

# Estado de plataformas
curl http://localhost:8000/telegram/status | jq
curl http://localhost:8000/whatsapp/status | jq
curl http://localhost:8000/discord/status | jq
```

### Reinicio de Servicios

```bash
# Reiniciar todo
docker-compose restart

# Reiniciar solo el bot
docker-compose restart bot-agent

# Reiniciar plataforma específica via API
curl -X POST http://localhost:8000/telegram/restart
curl -X POST http://localhost:8000/whatsapp/restart  
curl -X POST http://localhost:8000/discord/restart
```

## 📄 Licencia

Este proyecto está licenciado bajo GNU Affero General Public License v3.0 - ver el archivo [LICENSE](LICENSE) para detalles.

## 🤝 Contribuir

1. Fork del proyecto
2. Crear branch para feature (`git checkout -b feature/AmazingFeature`)
3. Commit cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push al branch (`git push origin feature/AmazingFeature`)  
5. Abrir Pull Request

## 📞 Soporte

- **Comunidad MeshChile**: [links.meshchile.cl](https://links.meshchile.cl)
- **Issues**: [GitHub Issues](https://github.com/Mesh-Chile/MeshChile-FAQ-Agent/issues)
- **Wiki**: [wiki.meshchile.cl](https://wiki.meshchile.cl)

---

**Desarrollado con ❤️ para la comunidad Mesh Chile 🇨🇱 por [Raztor](https://github.com/raztor)**