from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from flask import Flask
from threading import Thread
import config, handlers

app_web = Flask(__name__)
@app_web.route('/')
def home(): return "Dino Bot is alive!"
def run_web(): app_web.run(host='0.0.0.0', port=8080)

def main():
    Thread(target=run_web).start()
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("game", handlers.game_command))
    app.add_handler(CommandHandler("addword", handlers.addword_command))
    app.add_handler(CallbackQueryHandler(handlers.button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.check_guess))
    app.run_polling()

if __name__ == "__main__": main()
