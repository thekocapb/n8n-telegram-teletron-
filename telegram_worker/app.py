import os
import base64
from io import BytesIO
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False
    print("⚠️ qrcode not installed")

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import UsernameNotOccupiedError, PeerIdInvalidError

TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH", "")
SESSION_FILE = "/app/session/bot.session"

app = FastAPI(title="Telegram API for n8n")
client: Optional[TelegramClient] = None

class SendMsg(BaseModel):
    to: str
    message: str

class QrReq(BaseModel):
    text: str

@app.on_event("startup")
async def startup():
    global client
    if not TG_API_ID or not TG_API_HASH:
        print("❌ TG_API_ID или TG_API_HASH пустые!")
        return
    
    try:
        client = TelegramClient(SESSION_FILE, TG_API_ID, TG_API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            print("❌ НЕ АВТОРИЗОВАН! Запусти: docker compose run telegram_worker python")
            return
        me = await client.get_me()
        print(f"✅ АВТОРИЗОВАН: {me.first_name} (@{me.username or 'no username'})")
    except Exception as e:
        print(f"❌ Telegram startup error: {e}")

@app.get("/health")
async def health():
    if client is None:
        return {"ok": False, "error": "client not initialized"}
    return {"ok": True, "authorized": await client.is_user_authorized()}

@app.get("/chats")
async def list_chats():
    if not client or not await client.is_user_authorized():
        raise HTTPException(503, "Telegram not ready")
    
    chats = []
    async for dialog in client.iter_dialogs(limit=50):
        chats.append({
            "id": str(dialog.id),
            "title": dialog.title or "No title",
            "type": "user" if dialog.is_user else "group" if dialog.is_group else "channel"
        })
    return chats

@app.post("/qr")
async def qr(req: QrReq):
    if not HAS_QRCODE:
        raise HTTPException(503, "qrcode not installed")
    img = qrcode.make(req.text)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return {"png_base64": base64.b64encode(buf.getvalue()).decode("ascii")}

@app.get("/debug_entity/{to:path}")
async def debug_entity(to: str):
    if not client:
        raise HTTPException(503, "Telegram client not ready")
    
    try:
        entity = await client.get_entity(to)
        return {
            "ok": True,
            "id": str(entity.id),
            "title": getattr(entity, "title", getattr(entity, "first_name", getattr(entity, "username", "no title"))),
            "type": str(type(entity).__name__)
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def get_entity(to: str):
    if not client:
        raise HTTPException(503, "Telegram client not ready")
    
    if to.lower() == "me":
        return await client.get_me()
    
    try:
        # ID как int
        return await client.get_entity(int(to))
    except (ValueError, PeerIdInvalidError, UsernameNotOccupiedError):
        pass
    
    # @username
    if to.startswith('@'):
        try:
            from telethon.tl.functions.contacts import ResolveUsernameRequest
            result = await client(ResolveUsernameRequest(to[1:]))
            return result.users[0] if result.users else result.chats[0]
        except:
            pass
    
    raise HTTPException(status_code=400, detail=f"Cannot resolve '{to}'")

@app.post("/send_message")
async def send_message(req: SendMsg):
    try:
        entity = await get_entity(req.to)
        message = await client.send_message(entity, req.message)
        return {"sent": True, "message_id": message.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Send failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8099)
