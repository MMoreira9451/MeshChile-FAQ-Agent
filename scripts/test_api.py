# test_api.py
"""
Script para probar la API REST
"""
import asyncio
import httpx


async def test_api():
    """Prueba la API REST"""

    base_url = "http://localhost:8000"

    async with httpx.AsyncClient() as client:
        # Test health check
        print("🏥 Probando health check...")
        response = await client.get(f"{base_url}/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")

        # Test chat endpoint
        print("\n💬 Probando chat endpoint...")
        chat_payload = {
            "message": "Hola, ¿cómo estás?",
            "session_id": "test_api_001",
            "platform": "api_test"
        }

        response = await client.post(f"{base_url}/chat", json=chat_payload)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")

        # Test session info
        print("\n📊 Probando info de sesión...")
        response = await client.get(f"{base_url}/session/test_api_001")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")


if __name__ == "__main__":
    asyncio.run(test_api())