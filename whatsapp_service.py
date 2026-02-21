# services/whatsapp_service.py
import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")

if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_WHATSAPP_FROM:
    raise RuntimeError(
        "Missing Twilio config. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM in .env"
    )

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def send_whatsapp(phone: str, message: str):
    """
    phone must be in format: whatsapp:+91XXXXXXXXXX
    """
    msg = client.messages.create(
        from_=TWILIO_WHATSAPP_FROM,
        to=phone,
        body=message
    )

    return {
        "sid": msg.sid,
        "status": msg.status
    }
