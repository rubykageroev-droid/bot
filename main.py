from app.bot import DatingBot
from app.config import load_settings


def main() -> None:
    settings = load_settings()
    bot = DatingBot(settings)
    bot.run()


if __name__ == "__main__":
    main()
