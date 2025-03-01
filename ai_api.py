from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Iterator, Optional, List, Dict, Any
from phi.agent import Agent, RunResponse
from phi.tools.sql import SQLTools
from phi.model.groq import Groq
from phi.model.google import Gemini
from dotenv import load_dotenv
import os
import requests
import json
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from selenium_main import get_policy_info

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# USMSGH API Configuration
SMS_API_TOKEN = os.getenv("SMS_API_TOKEN")  # Add this to your .env file
SMS_SENDER_ID = os.getenv("SMS_SENDER_ID", "brainDoc")  # Default sender ID
SMS_API_BASE_URL = "https://webapp.usmsgh.com/api"

# Initialize the AI agent
policy_finder = Agent(
    tools=[get_policy_info],
    model=Groq(id='llama3-70b-8192'),
    markdown=True,
    instructions=[
        'The user will give you a Vehicle number or policy number'
        'When Given the query find the car number or Policy number and insert it into the tool function paramater as a string and run',
        'Give the Tool results to the user',
        'Return the details in a well formatted clean markdown and not json '
        'Add a line break for every policy detail item'
    ],
    add_context=True
)

class ChatRequest(BaseModel):
    message: str

class SMSWebhookRequest(BaseModel):
    from_number: str
    message: str
    uid: str

class SMSResponse(BaseModel):
    recipient: str
    sender_id: str
    type: str = "plain"
    message: str
    schedule_time: Optional[str] = None

# Existing chat endpoint
@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        response = policy_finder.run(request.message)
        return {"response": response.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# SMS webhook endpoint to receive inbound SMS
@app.post("/sms/webhook")
async def sms_webhook(request: Request):
    try:
        # Get the raw body as the USMSGH might send data in different format than our model
        body = await request.json()
        
        # Extract the needed information
        # Adapt this based on the actual format the webhook receives
        from_number = body.get("from")
        message_content = body.get("message")
        message_uid = body.get("uid", "")
        
        if not from_number or not message_content:
            raise HTTPException(status_code=400, detail="Missing required SMS data")
        
        # Process the message with the AI agent
        response = policy_finder.run(message_content)
        
        # Format the response for SMS (remove markdown and limit length if needed)
        sms_response_text = format_response_for_sms(response.content)
        
        # Send SMS response back to the user
        send_result = send_sms(from_number, sms_response_text)
        
        return {"status": "success", "message": "SMS processed and response sent", "details": send_result}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing SMS: {str(e)}")

# Endpoint to manually fetch inbound SMS messages
@app.post("/check/inbound-sms")
async def check_inbound_sms():
    try:
        inbound_messages = fetch_inbound_sms()
        
        # Process each message with the AI agent and send responses
        responses = []
        for msg in inbound_messages:
            from_number = msg.get("from")
            message_content = msg.get("message")
            
            # Process with AI
            ai_response = policy_finder.run(message_content)
            sms_response_text = format_response_for_sms(ai_response.content)
            
            # Send response
            send_result = send_sms(from_number, sms_response_text)
            responses.append({
                "from": from_number,
                "original_message": message_content,
                "response": sms_response_text,
                "send_status": send_result
            })
        
        return {"status": "success", "processed_messages": len(responses), "details": responses}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking inbound SMS: {str(e)}")

def format_response_for_sms(response_text: str) -> str:
    """Format the AI response to be SMS-friendly."""
    # Remove markdown formatting
    # This is a simple approach - you might need more comprehensive markdown stripping
    response_text = response_text.replace("*", "")
    response_text = response_text.replace("#", "")
    response_text = response_text.replace("`", "")
    
    # Limit length if needed (SMS usually has character limits)
    if len(response_text) > 800:  # SMS can typically handle more, but keeping it reasonable
        response_text = response_text[:797] + "..."
    
    return response_text

def send_sms(recipient: str, message: str) -> Dict[str, Any]:
    """Send SMS response using the USMSGH API."""
    if not SMS_API_TOKEN:
        raise ValueError("SMS_API_TOKEN not configured")
    
    headers = {
        "Authorization": f"Bearer {SMS_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    payload = {
        "recipient": recipient,
        "sender_id": SMS_SENDER_ID,
        "type": "plain",
        "message": message
    }
    
    response = requests.post(
        f"{SMS_API_BASE_URL}/sms/send",
        headers=headers,
        json=payload
    )
    
    if response.status_code != 200:
        return {"status": "error", "details": response.text}
    
    return response.json()

def fetch_inbound_sms() -> List[Dict[str, Any]]:
    """Fetch inbound SMS messages from the USMSGH API."""
    if not SMS_API_TOKEN:
        raise ValueError("SMS_API_TOKEN not configured")
    
    headers = {
        "Authorization": f"Bearer {SMS_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    payload = {
        "direction": "to",
        "request_type": "true"
    }
    
    response = requests.post(
        f"{SMS_API_BASE_URL}/sms/get/inbound",
        headers=headers,
        json=payload
    )
    
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    
    result = response.json()
    # Extract the actual messages from the response
    if "data" in result and isinstance(result["data"], list):
        return result["data"]
    return []

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)