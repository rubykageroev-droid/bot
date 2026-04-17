from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    db_path: str = "bot.db"



def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return Settings(bot_token=token, db_path=os.getenv("DB_PATH", "bot.db"))
