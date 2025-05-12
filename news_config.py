import os
from dotenv import load_dotenv
load_dotenv(dotenv_path=".news.env")
DB_DSN = os.getenv("DB_DSN")
API_TOKEN = os.getenv("API_TOKEN")
