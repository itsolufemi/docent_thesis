import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("QMUL_JUPYTER_TOKEN")

BASE_URL = (
    "https://hub.comp-teach.qmul.ac.uk/"
    "user/ec25326"
)

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

response = requests.post(
    f"{BASE_URL}/api/terminals",
    headers=headers,
    timeout=30
)

print("Status:", response.status_code)
print(response.text)