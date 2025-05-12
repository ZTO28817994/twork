import os
from dotenv import load_dotenv

load_dotenv(dotenv_path='.lzbot.env')
API_TOKEN = os.getenv("BOT_TOKEN")
POSTGRES_DSN = os.getenv("POSTGRES_DSN")
BOT_MODE = os.getenv("BOT_MODE", "polling").lower()

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")
WEBAPP_HOST = os.getenv("WEBAPP_HOST")

WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", 10000))


