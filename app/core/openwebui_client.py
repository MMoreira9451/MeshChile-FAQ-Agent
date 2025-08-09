# app/core/openwebui_client.py
import httpx
import json
from typing import Dict, List, Optional
from .config import settings


class OpenWebUIClient:
    def __init__(self):
        self.base_url = settings.OPENWEBUI_BASE_URL.rstrip('/')
        self.api_key = settings.OPENWEBUI_API_KEY
        self.model_name = settings.MODEL_NAME
        self.timeout = settings.MODEL_TIMEOUT
        self.temperature = settings.MODEL_TEMPERATURE

    async def chat_completion(
            self,
            messages: List[Dict[str, str]],
            stream: bool = False
    ) -> str:
        """Envía mensajes a Open Web UI usando formato OpenAI"""

        headers = {
            "Content-Type": "application/json"
        }

        # Añadir auth si está configurado
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": stream,
            "temperature": self.temperature
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat/completions",
                    json=payload,
                    headers=headers
                )

                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    error_detail = response.text if response.text else "Unknown error"
                    raise Exception(f"OpenWebUI error {response.status_code}: {error_detail}")

        except httpx.TimeoutException:
            raise Exception(f"Timeout connecting to OpenWebUI after {self.timeout}s")
        except httpx.ConnectError:
            raise Exception(f"Cannot connect to OpenWebUI at {self.base_url}")
        except Exception as e:
            raise Exception(f"OpenWebUI client error: {str(e)}")

    async def health_check(self) -> Dict:
        """Verifica el estado de OpenWebUI"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")

                return {
                    "status": "healthy" if response.status_code == 200 else "unhealthy",
                    "status_code": response.status_code,
                    "base_url": self.base_url,
                    "model": self.model_name
                }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "base_url": self.base_url,
                "model": self.model_name
            }
