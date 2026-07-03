import httpx
from config import settings

def check_llm_status() -> dict:
    url = f"{settings.ollama_base_url}/api/tags"
    try:
        response =httpx.get(url, timeout=10.0)
        response.raise_for_status()

        data = response.json()
        models = data.get("models", [])

        available_model_names = [
            model.get("name", "")
            for model in models
            if model.get("name")
        ]

        configured_model_available = settings.ollama_model in available_model_names

        if configured_model_available:
            message = 'llm is reachable and the configured model is available'
        else: 
            message = (
                "llm is reachable but the configured model is not available. "
                "Check OLLAMA_MODEL in your .env file."
            )

        return {
            "reachable": True,
            "base_url": settings.ollama_base_url,
            "configured_model": settings.ollama_model,
            "available_models": available_model_names,
            "message": message
        }
    
    except httpx.ConnectError:
        return {
            "reachable": False,
            "base_url": settings.ollama_base_url,
            "configured_model": settings.ollama_model,
            "available_models": [],
            "message": "error: couldn't connect the llm"
        }
    
    except Exception as error:
        return {
            "reachable": False,
            "base_url": settings.ollama_base_url,
            "configured_model": settings.ollama_model,
            "available_models": [],
            "message": f"error: {error}"
        }


def generate_llm_response(prompt: str) -> str:
    url = f"{settings.ollama_base_url}/api/generate"

    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False
    }

    try:
        response = httpx.post(url, json=payload, timeout=120.0)
        response.raise_for_status()

        data = response.json()
        return data.get("response", "").strip()
    
    except httpx.ConnectError:
        return "error: couldn't connect the llm"
    
    except httpx.HTTPStatusError as error:
        return f"ollama error: {error.response.status_code} - {error.response.text}"
    
    except Exception as error:
        return f"error: {error}"