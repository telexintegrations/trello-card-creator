import asyncio
import json
import hmac
import hashlib
from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import httpx


class Setting(BaseModel):
    label: str
    type: str
    required: bool
    default: str


class MessagePayload(BaseModel):
    channel_id: str
    return_url: str
    settings: List[Setting]
    message: dict


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://staging.telextest.im",
        "http://telextest.im",
        "https://staging.telex.im",
        "https://telex.im",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/logo")
def get_logo():
    return FileResponse("trello-logo.png")


@app.get("/integration.json")
def get_integration_json(request: Request):
    base_url = str(request.base_url).rstrip("/")

    return {
        "data": {
            "date": {"created_at": "2025-02-20", "updated_at": "2025-02-20"},
            "descriptions": {
                "app_name": "Trello Card Creator",
                "app_description": "Create Trello cards from Telex messages",
                "app_logo": f"{base_url}/logo",
                "app_url": base_url,
                "background_color": "#fff",
            },
            "is_active": False,
            "integration_type": "output",
            "key_features": [
                "- Automatically creates Trello cards",
                "- Supports multiple boards",
            ],
            "integration_category": "Product Management",
            "author": "Nadduli Daniel",
            "website": base_url,
            "settings": [
                {
                    "label": "Trello API Key",
                    "type": "text",
                    "required": True,
                    "default": "",
                },
                {
                    "label": "Trello Token",
                    "type": "text",
                    "required": True,
                    "default": "",
                },
                {"label": "Board ID", "type": "text", "required": True, "default": ""},
                {"label": "List ID", "type": "text", "required": True, "default": ""},
                {
                    "label": "Webhook Secret",
                    "type": "text",
                    "required": True,
                    "default": "",
                },
            ],
            "target_url": f"{base_url}/webhook",
            "webhook_events": ["message.created"],
        }
    }


async def create_trello_card(payload: MessagePayload):
    """Background task to create Trello cards"""
    settings = {s.label: s.default for s in payload.settings}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.trello.com/1/cards",
                params={
                    "key": settings["Trello API Key"],
                    "token": settings["Trello Token"],
                    "idList": settings["List ID"],
                },
                json={
                    "name": payload.message.get("text", "New Task from Telex"),
                    "desc": f"From Telex channel {payload.channel_id}\n"
                    f"Author: {payload.message.get('author', 'Unknown')}\n"
                    f"Timestamp: {payload.message.get('timestamp', '')}",
                },
            )
            response.raise_for_status()

    except Exception as e:
        print(f"Error creating Trello card: {str(e)}")


def verify_signature(request: Request, secret: str):
    signature = request.headers.get("X-Telex-Signature")
    body = request.body()

    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")

    digest = hmac.new(secret.encode(), msg=body, digestmod=hashlib.sha256).hexdigest()

    if not hmac.compare_digest(digest, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


@app.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle incoming Telex webhooks"""
    try:
        settings = json.loads(request.headers.get("X-Telex-Settings"))
        secret = next(s["default"] for s in settings if s["label"] == "Webhook Secret")

        verify_signature(request, secret)

        payload_data = await request.json()
        payload = MessagePayload(**payload_data)

        background_tasks.add_task(create_trello_card, payload)

        return JSONResponse(content={"status": "processing"})

    except Exception as e:
        return JSONResponse(
            status_code=400, content={"status": "error", "detail": str(e)}
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
