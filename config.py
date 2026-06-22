import os
from dotenv import load_dotenv

load_dotenv()

def get_int(name: str, default=0):
    try:
        return int(os.getenv(name, default))
    except:
        return default

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

CHANNEL_ID = get_int("CHANNEL_ID")
ADMIN_ID = get_int("ADMIN_ID")
PORT = get_int("PORT", 8000)
