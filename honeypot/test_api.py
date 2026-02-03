import requests
import time

URL = "http://localhost:8000/scam-detect"
HEADERS = {"x-api-key": "12345"}
SESSION_ID = f"test-session-{int(time.time())}"

payload = {
    "sessionId": SESSION_ID,
    "message": {
        "sender": "scammer",
        "text": "Hello, your bank account is blocked. Please send 5000 rs to 9876543210@upi to unblock it immediately or click https://bit.ly/fake-bank.",
        "timestamp": int(time.time())
    },
    "conversationHistory": [],
    "metadata": {}
}

try:
    print(f"Sending request to {URL}...")
    response = requests.post(URL, json=payload, headers=HEADERS)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")
