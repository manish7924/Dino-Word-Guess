import asyncio
import time
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import game_state, config

# Croco 2.0 AI Integration setup
import google.generativeai as genai
from PIL import Image

if config.CROCO_API_KEY:
    genai.configure(api_key=config.CROCO_API_KEY)
    # Using gemini-2.5-flash as the underlying driver for Croco 2.0 engine efficiency
    ai_model = genai.GenerativeModel('gemini-2.5-flash')
else:
    ai_model = None

AUTO_DROP_SECONDS = 120 

HELP_TEXT = (
    "🐊 <b>Crocodile Word Guess & AI</b>\n\n"
    "<b>How to play Crocodile Game:</b>\n"
    "1️⃣ /game — volunteer as the Crocodile leader by tapping the button.\n"
    "2️⃣ Leader uses <b>See word</b> 🔍 to view the hidden word.\n"
    "3️⃣ Give explanations or gestures in chat — <b>don't type or say the word itself!</b>\n"
    "4️⃣ Everyone else types text messages to guess.\n"
    "5️⃣ First correct guess wins a point and becomes the next Crocodile!\n\n"
    "<b>🤖 Croco 2.0 Multimodal AI Features:</b>\n"
    "• Type <code>/ask &lt;your question&gt;</code> to chat with Croco 2.0.\n"
    "• Send a <b>Photo</b> with the word <code>/ask</code> in the caption for visual AI analysis!\n\n"
    "<b>Commands:</b>\n"
    "/game — start or check the current round\n"
    "/scores — leaderboard metrics\n"
    "/addword — suggest a new word\n"
    "/ask — query the Croco 2.0 AI engine\n"
)

def leader_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 See word",    callback_data="see"),
            InlineKeyboardButton("✏️ Write word",  callback_data="write"),
        ],
        [
            InlineKeyboardButton("🔄 Change word", callback_data="change"),
            InlineKeyboardButton("❌ Drop lead",   callback_data="drop"),
        ],
    ])

def volunteer_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🐊 I want to be the Crocodile!", callback_data="lead"),
    ]])

def new_game_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🎲 Start next round!", callback_data="newgame"),
    ]])

def encode_word(word):
    return word.replace("_", "\u2019")

def decode_word(encoded):
    return encoded.replace("\u2019", "_")

# ── Auto-drop task ─────────────────────────────────────────────────────────────
async def schedule_auto_drop(chat_id: int, leader_id: int, bot):
    while True:
        await asyncio.sleep(AUTO_DROP_SECONDS)
        game = game_state.active_games.get(chat_id)
        if not game or not game["is_active"] or game["leader_id"] != leader_id:
            return

        idle_secs = time.time() - game.get("last_activity", 0)
        if idle_secs < AUTO_DROP_SECONDS:
            remaining = AUTO_DROP_SECONDS - idle_secs
            await asyncio.sleep(remaining)
            continue 

        leader_name = game["leader_name"]
        game_state.drop_leader(chat_id)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f"⏰ <b>{leader_name}</b> took too long to mimic — Crocodile role dropped!\n🐊 Who wants to step up?",
                parse_mode="HTML",
                reply_markup=volunteer_keyboard(),
            )
        except Exception:
            pass
        return

def fire_auto_drop(chat_id: int, leader_id: int, bot):
    asyncio.create_task(schedule_auto_drop(chat_id, leader_id, bot))

# ── Commands ───────────────────────────────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html("👋 Welcome to <b>Crocodile Word Game & AI Bot</b>! 🐊\n\n" + HELP_TEXT)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(HELP_TEXT)

async def scores_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    players = [s for s in game_state.user_stats.values() if chat_id in s.get("played_in", set())]
    if not players:
        return await update.message.reply_text("No scores recorded yet! Start via /game")

    players.sort(key=lambda s: (s["wins"] - s.get("penalties", 0), s["wins"]), reverse=True)
    lines = ["🏆 <b>Crocodile Leaderboard</b>\n"]
    for i, p in enumerate(players[:10], 1):
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}."
        penalties = p.get("penalties", 0)
        net = p["wins"] - penalties
        lines.append(f"{medal} <b>{p['name']}</b> — {p['wins']} wins · {p['led']} times leader (Net: {net:+d})")
    await update.message.reply_html("\n".join(lines))

async def addword_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /addword <word>")
    word = context.args[0].lower().strip()
    if not word.isalpha() or len(word) > 30:
        return await update.message.reply_text("Invalid word selection.")
    
    user = update.effective_user
    game_state.add_pending(word, user.first_name, user.id, update.effective_chat.id)
    encoded = encode_word(word)
    
    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"app_{encoded}"),
        InlineKeyboardButton("❌ Reject",  callback_data=f"rej_{encoded}"),
    ]]
    try:
        await context.bot.send_message(
            chat_id=config.OWNER_ID,
            text=f"📝 <b>Croco 2.0 Word Suggestion</b>\nWord: {word.capitalize()}\nFrom: {user.first_name}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await update.message.reply_text("✅ Word queued for Crocodile review panel!")
    except Exception:
        await update.message.reply_text("Failed to alert owner.")

async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return await update.message.reply_text("⛔ Admin command only.")
    if not game_state.pending_words:
        return await update.message.reply_text("No pending words.")
    for word, info in list(game_state.pending_words.items()):
        encoded = encode_word(word)
        keyboard = [[InlineKeyboardButton("✅ Approve", callback_data=f"app_{encoded}"), InlineKeyboardButton("❌ Reject", callback_data=f"rej_{encoded}")]]
        await update.message.reply_html(f"Word: <b>{word.capitalize()}</b>\nFrom: {info['from_name']}", reply_markup=InlineKeyboardMarkup(keyboard))

async def game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = game_state.active_games.get(chat_id)

    if game and game.get("is_active"):
        markup = leader_keyboard() if user.id == game["leader_id"] else None
        await update.message.reply_html(f"🐊 <b>{game['leader_name']}</b> is currently acting out the secret word!", reply_markup=markup)
    else:
        await update.message.reply_html("🐊 No active Crocodile game found here. Who wants to take the lead?", reply_markup=volunteer_keyboard())

# ── Croco 2.0 AI Core Handlers ──────────────────────────────────────────────────
async def ask_croco_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Text-only query channel to Croco 2.0"""
    if not ai_model:
        return await update.message.reply_text("🤖 Croco 2.0 engine is offline. CROCO_API_KEY missing.")
    
    query = " ".join(context.args)
    if not query:
        return await update.message.reply_text("Please provide a prompt! Example: /ask Tell me a joke about crocodiles.")
    
    status_msg = await update.message.reply_text("🤖 <i>Croco 2.0 is processing your thought...</i>", parse_mode="HTML")
    try:
        response = ai_model.generate_content(f"You are Croco 2.0, a witty, super intelligent Crocodile AI assistant. Answer this: {query}")
        await status_msg.edit_text(response.text)
    except Exception as e:
        await status_msg.edit_text(f"❌ Error generating response: {str(e)}")

async def croco_multimodal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes images with /ask caption commands"""
    caption = update.message.caption or ""
    if not caption.startswith("/ask"):
        return # Skip unless explicit request

    if not ai_model:
        return await update.message.reply_text("🤖 Croco 2.0 Vision engine configuration missing.")

    status_msg = await update.message.reply_text("🐊 <i>Croco 2.0 AI is analyzing your image...</i>", parse_mode="HTML")
    try:
        prompt_text = caption.replace("/ask", "").strip() or "Describe what you see in this image relative to the theme."
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        image = Image.open(io.BytesIO(photo_bytes))
        response = ai_model.generate_content([f"[Croco 2.0 Engine Vision Prompt]: {prompt_text}", image])
        await status_msg.edit_text(response.text)
    except Exception as e:
        await status_msg.edit_text(f"❌ Vision processing failed: {str(e)}")

# ── Callback buttons & Messages ─────────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    caller_id = query.from_user.id
    chat_id = query.message.chat_id

    if data in ("lead", "newgame"):
        existing = game_state.active_games.get(chat_id)
        if existing and existing.get("is_active"):
            return await query.answer("Game already ongoing!", show_alert=True)
        game_state.start_new_round(chat_id, caller_id, query.from_user.first_name)
        fire_auto_drop(chat_id, caller_id, context.bot)
        await query.answer()
        await context.bot.send_message(chat_id=chat_id, text=f"🐊 <b>{query.from_user.first_name}</b> became the Crocodile! Don't name the word!", parse_mode="HTML", reply_markup=leader_keyboard())
        return

    # Approvals / Rejections
    if data.startswith("app_") or data.startswith("rej_"):
        if caller_id != config.OWNER_ID:
            return await query.answer("Access denied.", show_alert=True)
        word = decode_word(data[4:])
        if data.startswith("app_"):
            config.add_new_word(word)
            game_state.remove_pending(word)
            await query.edit_message_text(f"✅ Word '{word.capitalize()}' joined the swamp selection!")
        else:
            game_state.remove_pending(word)
            await query.edit_message_text(f"❌ Word '{word.capitalize()}' rejected.")
        await query.answer()
        return

    # Active round actions
    game = game_state.active_games.get(chat_id)
    if not game or not game["is_active"]:
        return await query.answer("No active session.", show_alert=True)

    if data in ("see", "write", "change", "drop"):
        if caller_id != game["leader_id"] and not (data == "drop" and caller_id == config.OWNER_ID):
            return await query.answer("You are not the designated Crocodile!", show_alert=True)
        game_state.update_activity(chat_id)

    if data == "see":
        await query.answer(f"🐊 Your word: {game['word'].upper()}", show_alert=True)
    elif data == "write":
        try:
            await context.bot.send_message(chat_id=caller_id, text=f"🐊 Secret Word: <b>{game['word'].upper()}</b>", parse_mode="HTML")
            await query.answer("Sent to your DMs!")
        except:
            await query.answer("DM failed. PM the bot first.", show_alert=True)
    elif data == "change":
        new_w = game_state.change_word(chat_id)
        await query.answer(f"🔄 Swapped! New Word: {new_w.upper()}", show_alert=True)
    elif data == "drop":
        game_state.drop_leader(chat_id)
        await query.edit_message_text("🐊 The Crocodile went back to the river. Who is next?", reply_markup=volunteer_keyboard())

async def check_guess_or_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = game_state.active_games.get(chat_id)
    
    if not game or not game["is_active"]:
        return # Standard conversation unmonitored if no game active

    sender = update.effective_user
    text = update.message.text.lower().strip()

    if sender.id == game["leader_id"]:
        game_state.update_activity(chat_id)
        if text == game["word"]:
            game_state.record_penalty(sender.id, sender.first_name, chat_id)
            await update.message.reply_html(f"⚠️ <b>{sender.first_name}</b>, you leaked the secret word! Penalty applied!")
        return

    if text == game["word"]:
        word = game["word"]
        game_state.drop_leader(chat_id)
        game_state.record_win(sender.id, sender.first_name, chat_id)
        
        await update.message.reply_html(f"🎉 <b>{sender.first_name}</b> caught the word: <b>{word.upper()}</b>!", reply_markup=new_game_keyboard())
        
        # Winner instantly escalates to active crocodile
        game_state.start_new_round(chat_id, sender.id, sender.first_name)
        fire_auto_drop(chat_id, sender.id, context.bot)
        await context.bot.send_message(chat_id=chat_id, text=f"🐊 <b>{sender.first_name}</b> is now the Crocodile!", parse_mode="HTML", reply_markup=leader_keyboard())
