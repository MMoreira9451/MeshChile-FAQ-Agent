# app/core/config_validator.py
"""
Validador de configuración simplificado para Redis
"""
import sys
from .config import settings


def validate_config():
    """Valida la configuración y muestra errores"""
    errors = []
    warnings = []

    # Validaciones requeridas
    if not settings.OPENWEBUI_BASE_URL:
        errors.append("OPENWEBUI_BASE_URL es requerido")

    if not settings.MODEL_NAME:
        errors.append("MODEL_NAME es requerido")

    # Validación de Redis
    if not settings.REDIS_URL and not settings.REDIS_HOST:
        errors.append("REDIS_URL o REDIS_HOST es requerido")

    # Validaciones de plataformas (opcional)
    if settings.WHATSAPP_ACCESS_TOKEN and not settings.WHATSAPP_VERIFY_TOKEN:
        errors.append("WHATSAPP_VERIFY_TOKEN requerido si usas WhatsApp")

    # Validaciones de puertos
    if not (1 <= settings.API_PORT <= 65535):
        errors.append("API_PORT debe estar entre 1 y 65535")

    # Mostrar resultados
    if errors:
        print("❌ Errores de configuración:")
        for error in errors:
            print(f"  - {error}")
        return False

    if warnings:
        print("⚠️  Advertencias de configuración:")
        for warning in warnings:
            print(f"  - {warning}")

    print("✅ Configuración válida")
    return True


def print_config_summary():
    """Muestra resumen de configuración"""
    print("\n📋 Resumen de configuración:")
    print(f"  🔗 Open Web UI: {settings.OPENWEBUI_BASE_URL}")
    print(f"  🤖 Modelo: {settings.MODEL_NAME}")
    print(f"  📡 API: {settings.API_HOST}:{settings.API_PORT}")
    print(f"  💾 Redis: {settings.redis_full_url}")

    # Plataformas habilitadas
    platforms = []
    if settings.TELEGRAM_BOT_TOKEN:
        platforms.append("Telegram")
    if settings.WHATSAPP_ACCESS_TOKEN:
        platforms.append("WhatsApp")
    if settings.DISCORD_BOT_TOKEN:
        platforms.append("Discord")

    if platforms:
        print(f"  📱 Plataformas: {', '.join(platforms)}")
    else:
        print(f"  📱 Plataformas: Solo API REST")


if __name__ == "__main__":
    if validate_config():
        print_config_summary()
    else:
        sys.exit(1)