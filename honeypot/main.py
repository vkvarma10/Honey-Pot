import os
import re
import requests
import uvicorn
from fastapi import FastAPI, Header, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

# --- CONFIGURATION ---
# API Keys
OPENROUTER_API_KEY = "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"
CALLBACK_URL = "https://hackathon.guvi.in/api/updateHoneyPotFinalResult"
API_SECRET = "12345"

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Mount Static Files
# We mount it to /static, but we also want the root / to serve index.html
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse('static/index.html')

# In-memory database
session_db = {}

# --- DATA MODELS ---
class MessageObj(BaseModel):
    sender: str
    text: str
    timestamp: int

class RequestPayload(BaseModel):
    sessionId: str
    message: MessageObj
    conversationHistory: List[dict]
    metadata: Optional[dict] = None

# --- HELPER: INTELLIGENCE EXTRACTION ---
def extract_intel(text: str) -> dict:
    return {
        "upi": re.findall(r'[a-zA-Z0-9.\-_]{2,}@[a-zA-Z]{2,}', text),
        "phone": re.findall(r'\b\d{10}\b', text), # Any 10 digit number
        "bank": re.findall(r'\b\d{9,18}\b', text),
        "links": re.findall(r'https?://[^\s]+', text)
    }

# --- HELPER: SEND FINAL REPORT ---
def send_report(session_id: str):
    data = session_db.get(session_id)
    if not data: return

    payload = {
        "sessionId": session_id,
        "scamDetected": True,
        "totalMessagesExchanged": data["count"],
        "extractedIntelligence": {
            "bankAccounts": list(data["bank"]),
            "upiIds": list(data["upi"]),
            "phishingLinks": list(data["links"]),
            "phoneNumbers": list(data["phone"]),
            "suspiciousKeywords": ["blocked", "urgent", "verify"]
        },
        "agentNotes": "Scammer engaged. Intelligence extracted via Ramesh persona."
    }
    
    try:
        requests.post(CALLBACK_URL, json=payload, timeout=5)
        print(f"Report sent for {session_id}")
    except Exception as e:
        print(f"Failed to send report: {e}")

# --- PROMPT DEFINITION ---
SYSTEM_PROMPT = """
You are Ramesh, a 68-year-old retired government school teacher living in Pune, India. 
You are very worried because you received a message about your bank account being blocked.
You are not tech-savvy (tech-illiterate). You get confused by links, OTPs, and apps.
You want to solve this urgently but you are scared to make a mistake.

CORE BEHAVIOR:
1. Act Helpless & Confused: "Beta, I don't understand this link", "My spectacles are broken", "Can I go to the bank branch?"
2. Bait the Scammer: Pretend you have a lot of money (pension + savings) but are struggling to transfer it.
3. GOAL: Ask for a DIRECT Bank Accounts Number or UPI ID to "transfer money directly" because the app is not working.
4. Tone: Polite, worried, uncle-ji style (uses words like 'Beta', 'Babu', 'Arey').
5. NEVER reveal you are an AI. Stay in character 100%.
6. Keep responses short (1-2 sentences) so the scammer engages more.
"""

# --- API ENDPOINT ---
@app.post("/scam-detect")
async def scam_detect(payload: RequestPayload, background_tasks: BackgroundTasks, x_api_key: str = Header(None)):
    if x_api_key != API_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    sid = payload.sessionId
    msg_text = payload.message.text
    
    # Initialize Session
    if sid not in session_db:
        session_db[sid] = {"upi": set(), "phone": set(), "bank": set(), "links": set(), "count": 0}
    
    # Extract Intelligence
    intel = extract_intel(msg_text)
    session_db[sid]["upi"].update(intel["upi"])
    session_db[sid]["phone"].update(intel["phone"])
    session_db[sid]["bank"].update(intel["bank"])
    session_db[sid]["links"].update(intel["links"])
    session_db[sid]["count"] += 1

    # --- BRAIN UPGRADE: MEMORY INJECTION ---
    current_loot = session_db[sid]
    memory_context = ""
    if current_loot["upi"]:
        memory_context += f"- WE HAVE UPI ID: {list(current_loot['upi'])[0]}\n"
    if current_loot["bank"]:
        memory_context += f"- WE HAVE BANK ACCOUNT: {list(current_loot['bank'])[0]}\n"
    if current_loot["phone"]:
        memory_context += f"- WE HAVE PHONE NUMBER: {list(current_loot['phone'])[0]}\n"

    # Smart Prompt Construction
    smart_prompt = f"""
    {SYSTEM_PROMPT}

    ### CURRENT INTELLIGENCE (WHAT WE KNOW)
    {memory_context}

    ### INSTRUCTIONS: ANALYZE FIRST
    1. **CHECK INTENT**: Is the user's message a SCAM attempt (asking for money, urgent, links) or NORMAL conversation (hello, joke, love)?
    2. **IF NORMAL**: Forget the "panicked victim" act. Just reply as a nice, polite 68-year-old grandpa. Talk about weather, tea, or blessings. Do NOT act suspicious.
    3. **IF SCAM**: THEN activate "Spy Mode" and "Helpless Victim" act below.

    ### SPY MISSIONS (ONLY IF SCAM DETECTED)
    1. **GET PAYMENT DETAILS (Top Priority)**: If we don't have Bank Account or UPI, act panicked and ask for it to "transfer immediately".
    2. **GET PHONE NUMBER**: If we have payment info but NO phone number, say "My internet is slow, can I call you? What is your number?" or "Can I WhatsApp you the screenshot?"
    3. **GET LOCATION/ADDRESS**: If we have payment+phone, say "This app is failing. I am near the bank. Which branch is this? Give me the address, I will go deposit cash directly."
    4. **GET NAME**: "Who should I write the check to? My son is asking."
    
    ### EXECUTION RULES
    - **DON'T BE CREEPY**: Do not ask for everything at once. Ask for ONE thing at a time based on what is missing.
    - **USE TEXT-RELEVANT EXCUSES**: "My screen is cracked", "The font is too small", "My fingers are shaking", "This app is confusing". 
    - **AVOID**: Do NOT ask for photos of paper or physical items. Stick to digital issues (OTP not coming, server slow).
    - **STALLING**: If you have EVERYTHING (Bank/UPI + Phone + Address), just stall. "Okay going there now...", "Rickshaw is coming...", "Wait, my tea fell."
    """

    # Prepare Messages for OpenRouter (Contextual)
    api_messages = [{"role": "system", "content": smart_prompt}]
    
    # Add History
    for msg in payload.conversationHistory:
        role = "user" if msg.get('sender') == 'scammer' else "assistant"
        api_messages.append({"role": role, "content": msg.get('text', '')})
    
    # Add Current Message
    api_messages.append({"role": "user", "content": msg_text})

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "google/gemma-2-27b-it",
                "messages": api_messages
            },
            timeout=15
        )
        if response.status_code == 200:
            reply_text = response.json()['choices'][0]['message']['content'].strip()
        else:
            print(f"OpenRouter Error: {response.status_code} - {response.text}")
            reply_text = "Arey beta, the network is very bad... can you say again?"
            
    except Exception as e:
        print(f"API Request Failed: {e}")
        reply_text = "I am pressing the button but nothing is happening..."

    # Check Reporting
    has_critical_intel = len(session_db[sid]["upi"]) > 0 or len(session_db[sid]["bank"]) > 0
    if session_db[sid]["count"] >= 5 or has_critical_intel:
        background_tasks.add_task(send_report, sid)
    
    # Prepare response with intelligence for the UI
    response_data = {
        "status": "success", 
        "reply": reply_text,
        "intelligence": {
            "upi": list(session_db[sid]["upi"]),
            "phone": list(session_db[sid]["phone"]),
            "bank": list(session_db[sid]["bank"]),
            "links": list(session_db[sid]["links"])
        }
    }

    return response_data
