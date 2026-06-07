import httpx
from config import settings

def generate_llm_response(prompt:str) -> str:
    url = f"{settings.ollama_base_url}/api/generate"

    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False
    }

    try:
        response = httpx.post(url, json=payload, timeout=60.0)
        response.raise_for_status()

        data = response.json()
        return data.get("response", "").strip()
    
    except httpx.ConnectError:
        return "error: couldn't connect the llm"
    
    except httpx.HTTPStatusError as error:
        return f"ollama error: {error.response.status_code} - {error.response.text}"
    
    except Exception as error:
        return f"error: {error}"