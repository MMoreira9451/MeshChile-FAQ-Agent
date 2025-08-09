# run.py
"""
Script principal de ejecución
"""
import uvicorn
import sys
import os

# Añadir el directorio actual al path para imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Ahora importar con path absoluto
from app.core.config import settings


def main():
    """Ejecuta el bot con validaciones básicas"""
    print("🚀 Iniciando Bot Agent...")

    # Verificaciones básicas
    required_vars = ['OPENWEBUI_BASE_URL', 'MODEL_NAME']
    missing = [var for var in required_vars if not getattr(settings, var, None)]

    if missing:
        print(f"❌ Variables requeridas faltantes: {', '.join(missing)}")
        print("💡 Verifica tu archivo .env")
        print(f"💡 Variables faltantes: {missing}")
        print(f"💡 Archivo .env existe: {os.path.exists('.env')}")
        sys.exit(1)

    print(f"📡 API: http://{settings.API_HOST}:{settings.API_PORT}")
    print(f"📖 Docs: http://{settings.API_HOST}:{settings.API_PORT}/docs")
    print(f"🔗 OpenWebUI: {settings.OPENWEBUI_BASE_URL}")
    print(f"🤖 Modelo: {settings.MODEL_NAME}")
    print(f"💾 Redis: {settings.redis_full_url}")
    print("🛑 Presiona Ctrl+C para detener\n")

    try:
        uvicorn.run(
            "app.main:app",
            host=settings.API_HOST,
            port=settings.API_PORT,
            reload=settings.API_DEBUG,
            log_level=settings.LOG_LEVEL.lower()
        )
    except KeyboardInterrupt:
        print("\n👋 Bot Agent detenido")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()