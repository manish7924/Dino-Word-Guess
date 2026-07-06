import sys
import logging
from telegram import BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from flask import Flask
from threading import Thread
import config, handlers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Dino Bot is alive!"

def run_web():
    app_web.run(host='0.0.0.0', port=3000)

async def post_init(application):
    commands = [
        BotCommand("start",   "Welcome message & how to play"),
        BotCommand("game",    "Start or check the current game"),
        BotCommand("addword", "Suggest a new word: /addword <word>"),
        BotCommand("scores",  "Show leaderboard for this chat"),
        BotCommand("pending", "Owner: review pending word suggestions"),
        BotCommand("help",    "Show help"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered with Telegram.")

def main():
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable is not set.")
        sys.exit(1)
    if config.OWNER_ID == 0:
        logger.warning("OWNER_ID is not set — /addword approvals won't reach you.")

    Thread(target=run_web, daemon=True).start()

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",   handlers.start_command))
    app.add_handler(CommandHandler("help",    handlers.help_command))
    app.add_handler(CommandHandler("game",    handlers.game_command))
    app.add_handler(CommandHandler("addword", handlers.addword_command))
    app.add_handler(CommandHandler("scores",  handlers.scores_command))
    app.add_handler(CommandHandler("pending", handlers.pending_command))
    app.add_handler(CallbackQueryHandler(handlers.button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.check_guess))

    logger.info("🦕 Dino Word Guess Bot is running...")
    app.run_polling(allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()
