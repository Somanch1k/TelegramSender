from pathlib import Path
from dotenv import load_dotenv
import os

# Загружаем переменные из .env
load_dotenv()

# Корневая папка проекта
BASE_DIR = Path(__file__).resolve().parent.parent

# Папки проекта
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
SESSION_DIR = BASE_DIR / "sessions"

# Создаём их автоматически
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
SESSION_DIR.mkdir(exist_ok=True)

# Telegram API
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

# Имя файла сессии
SESSION_NAME = "sender"