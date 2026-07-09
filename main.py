import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Set higher logging level for httpx to avoid spamming logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Token configuration (Replace with your actual Bot Token or load from environment/config)
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# The exact formatted help menu text
HELP_TEXT = """🐊❔ Game commands:

🎮 /game - start new game (🔤 /💠)
🛑 /stop - stop current game
🪧 /rules - know game rules
📊 /mystats - my game stats
📊 /ranking - top 25 players (current chat)
📊 /globalranking - top 25 global players
📊 /chatranking - top 10 chats
⚙️ /settings - user/group settings
❔ /help - show this message

🔤 Word Guess specific commands:

🎤 /hint - show hints by leader
➕ /addword - add word to dictionary
📖 /wordset - view current wordset"""


# --- Command Handlers ---

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responds with the full command menu list."""
    await update.message.reply_text(HELP_TEXT)


async def game_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Starts a brand new game session (Word Guess / Emoji mode)."""
    # TODO: Add your game initialization logic here
    await update.message.reply_text("🎮 Starting a new game! Choose your mode: Word Guess 🔤 or Element 💠.")


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stops and clears the current active game session in the group."""
    # TODO: Add your logic to terminate the current game session
    await update.message.reply_text("🛑 The current game has been stopped.")


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explains how the game is played."""
    rules_text = (
        "🪧 *Game Rules:*\n\n"
        "1. A leader or the bot sets a hidden word.\n"
        "2. Players take turns trying to guess the correct word.\n"
        "3. Use /hint if you need clues from the leader!"
    )
    await update.message.reply_text(rules_text, parse_mode="Markdown")


async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and displays the calling user's individual game stats."""
    user = update.effective_user
    # TODO: Fetch user stats from database
    await update.message.reply_text(f"📊 *Stats for {user.first_name}:*\nGames Played: 0\nWins: 0\nPoints: 0", parse_mode="Markdown")


async def ranking_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the top 25 players within the current chat/group."""
    # TODO: Query group-specific leaderboard from database
    await update.message.reply_text("📊 *Top 25 Players (Current Chat):*\n\n1. Loading ranking data...", parse_mode="Markdown")


async def globalranking_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the top 25 players across the entire global network of the bot."""
    # TODO: Query global leaderboard from database
    await update.message.reply_text("📊 *Top 25 Global Players:*\n\n1. Loading global ranking data...", parse_mode="Markdown")


async def chatranking_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the top 10 most active groups/chats."""
    # TODO: Query top chats from database
    await update.message.reply_text("📊 *Top 10 Chats:*\n\n1. Loading chat ranking data...", parse_mode="Markdown")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows individual users or group administrators to toggle bot settings."""
    # TODO: Implement user preference modifications or admin configuration menus
    await update.message.reply_text("⚙️ *Settings Menu:* Modify game preferences, language, or notification toggles.", parse_mode="Markdown")


async def hint_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the hint text provided by the game's designated leader."""
    # TODO: Check if a game is active and retrieve the current hint string
    await update.message.reply_text("🎤 *Hint:* No active hints available or no active game running right now.", parse_mode="Markdown")


async def addword_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows players to append a new word directly into the custom dictionary pool."""
    # Example parsing logic: /addword elephant
    if context.args:
        new_word = " ".join(context.args)
        # TODO: Save new_word into your database or word_list file
        await update.message.reply_text(f"➕ Added *'{new_word}'* to the custom dictionary pool!", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Please specify a word. Format: `/addword <word>`", parse_mode="Markdown")


async def wordset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the currently selected word list configuration or category."""
    # TODO: Pull active word list status/category
    await update.message.reply_text("📖 *Current Wordset:* Default Dictionary (All Categories).", parse_mode="Markdown")


# --- Main Application Loop ---

def main() -> None:
    """Starts the bot application."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    # Register Game Commands handlers
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("game", game_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("rules", rules_command))
    application.add_handler(CommandHandler("mystats", mystats_command))
    application.add_handler(CommandHandler("ranking", ranking_command))
    application.add_handler(CommandHandler("globalranking", globalranking_command))
    application.add_handler(CommandHandler("chatranking", chatranking_command))
    application.add_handler(CommandHandler("settings", settings_command))

    # Register Word Guess Specific handlers
    application.add_handler(CommandHandler("hint", hint_command))
    application.add_handler(CommandHandler("addword", addword_command))
    application.add_handler(CommandHandler("wordset", wordset_command))

    # Run the bot until the user presses Ctrl-C
    print("Bot is starting up... Press Ctrl-C to stop.")
    application.run_polling()


if __name__ == "__main__":
    main()
