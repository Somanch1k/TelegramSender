from pathlib import Path
import os
from datetime import datetime
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Корень проекта
BASE_DIR = Path(__file__).resolve().parent.parent

# Основные папки
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
SESSIONS_DIR = BASE_DIR / "sessions"

# Создаём папки автоматически
for folder in (DATA_DIR, LOGS_DIR, SESSIONS_DIR):
    folder.mkdir(exist_ok=True)

# Пути к файлам
DATABASE_PATH = DATA_DIR / "bot.db"
LOG_FILE = LOGS_DIR / "bot.log"
SESSION_FILE = SESSIONS_DIR / "sender"

# Telegram
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

CONTROL_GROUP_ID = int(os.getenv("CONTROL_GROUP_ID"))

# Часовой пояс (по умолчанию Киев)
TIMEZONE_NAME = os.getenv("TIMEZONE", "Europe/Kyiv")
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(TIMEZONE_NAME)
except Exception:
    TZ = None


def get_now():
    if TZ:
        return datetime.now(TZ)
    return datetime.now().astimezone()
