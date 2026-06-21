from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import game_state, config

async def addword_command(update, context):
    if not context.args: return await update.message.reply_text("Usage: /addword <word>")
    word = context.args[0].lower()
    keyboard = [[InlineKeyboardButton("✅ Approve", callback_data=f"app_{word}"), InlineKeyboardButton("❌ Reject", callback_data=f"rej_{word}")]]
    await context.bot.send_message(chat_id=config.OWNER_ID, text=f"New word suggestion: {word}", reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("Sent for approval!")

async def game_command(update, context):
    chat_id = update.effective_chat.id
    game = game_state.active_games.get(chat_id)
    if not game or not game.get("is_active"):
        kb = [[InlineKeyboardButton("🦕 I want to be a leader!", callback_data="lead")]]
        await update.message.reply_text("No active game.", reply_markup=InlineKeyboardMarkup(kb))
    else:
        kb = [[InlineKeyboardButton("🔎 See", callback_data="see"), InlineKeyboardButton("❌ Drop", callback_data="drop")]]
        await update.message.reply_text(f"🦕 {game['leader_name']} is leading!", reply_markup=InlineKeyboardMarkup(kb))

async def button_handler(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("app_"):
        config.add_new_word(data.split("_")[1])
        await query.edit_message_text("Approved!")
    elif data == "lead":
        game_state.start_new_round(query.message.chat_id, query.from_user.id, query.from_user.first_name)
        await query.edit_message_text("You are the leader!")
    elif data == "see":
        game = game_state.active_games.get(query.message.chat_id)
        if game: await query.answer(f"Word: {game['word']}", show_alert=True)
    elif data == "drop":
        game_state.drop_leader(query.message.chat_id)
        await query.edit_message_text("Lead dropped.")

async def check_guess(update, context):
    game = game_state.active_games.get(update.effective_chat.id)
    if game and game["is_active"] and update.message.text.lower() == game["word"]:
        game_state.drop_leader(update.effective_chat.id)
        await update.message.reply_text(f"🎉 Correct! The word was {game['word']}")
