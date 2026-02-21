# test_whatsapp_send.py

from whatsapp_service import send_whatsapp

if __name__ == "__main__":
    TEST_PHONE = "whatsapp:+919400763629"  # your number
    MESSAGE = "✅ WhatsApp test successful from backend!"

    result = send_whatsapp(TEST_PHONE, MESSAGE)
    print("WhatsApp sent:", result)