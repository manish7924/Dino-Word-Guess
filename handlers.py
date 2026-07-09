import asyncio
import time
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import game_state, config

# Dino 2.0 AI Integration setup
import google.generativeai as genai
from PIL import Image

if config.DINO_API_KEY:
    genai.configure(api_key=config.DINO_API_KEY)
    # Powering Dino 2.0 Engine with fast multimodal features
    ai_model = genai.GenerativeModel('gemini-2.5-flash')
else:
    ai_model = None

# How long (seconds) before the bot auto-drops an idle leader
AUTO_DROP_SECONDS = 120  # 2 minutes

HELP_TEXT = (
    "🦕 <b>Dino Word Guess & AI</b>\n\n"
    "<b>How to play Dino Game:</b>\n"
    "1️⃣ /game — volunteer as the Dino leader by tapping the button.\n"
    "2️⃣ Leader uses <b>See word</b> 🔍 to view the hidden word.\n"
    "3️⃣ Give explanations or gestures in chat — <b>don't type or say the word itself!</b>\n"
    "4️⃣ Everyone else types text messages to guess.\n"
    "5️⃣ First correct guess wins a point and becomes the next Dino!\n\n"
    "<b>🤖 Dino 2.0 Multimodal AI Features:</b>\n"
    "• Type <code>/ask &lt;your question&gt;</code> to chat with Dino 2.0.\n"
    "• Send a <b>Photo</b> with the word <code>/ask</code> in the caption for visual AI analysis!\n\n"
    "<b>Commands:</b>\n"
    "/game — start or check the current round\n"
    "/scores — leaderboard metrics\n"
    "/addword — suggest a new word\n"
    "/ask — query the Dino 2.0 AI engine\n"
    "/help — show this message\n\n"
    "⚠️ <i>In groups, Privacy Mode must be OFF in BotFather for guesses to work.</i>"
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
        InlineKeyboardButton("🦕 I want to be the Dino!", callback_data="lead"),
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
    """Loop until the leader has been idle for AUTO_DROP_SECONDS, then drop them."""
    while True:
        await asyncio.sleep(AUTO_DROP_SECONDS)

        game = game_state.active_games.get(chat_id)
        # Stop watching if game ended or a different leader took over
        if not game or not game["is_active"] or game["leader_id"] != leader_id:
            return

        idle_secs = time.time() - game.get("last_activity", 0)
        if idle_secs < AUTO_DROP_SECONDS:
            # Leader was active since we last checked — wait out the remaining gap
            remaining = AUTO_DROP_SECONDS - idle_secs
            await asyncio.sleep(remaining)
            continue  # re-check at top of loop

        # Leader has been idle long enough — drop them
        leader_name = game["leader_name"]
        old_msg_id = game.get("control_message_id")
        game_state.drop_leader(chat_id)
        
        # Clear out old dashboard inline inputs out-of-band
        if old_msg_id:
            try:
                await bot.edit_message_reply_markup(chat_id=chat_id, message_id=old_msg_id, reply_markup=None)
            except Exception:
                pass

        try:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⏰ <b>{leader_name}</b> was idle too long — Dino lead dropped!\n"
                    "🦕 Who wants to step up?"
                ),
                parse_mode="HTML",
                reply_markup=volunteer_keyboard(),
            )
        except Exception:
            pass
        return


def fire_auto_drop(chat_id: int, leader_id: int, bot):
    """Non-async helper — schedules the auto-drop coroutine as a background task."""
    asyncio.create_task(schedule_auto_drop(chat_id, leader_id, bot))


# ── Commands ───────────────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "👋 Welcome to <b>Dino Word Game & AI Bot</b>! 🦕\n\n" + HELP_TEXT
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(HELP_TEXT)


async def scores_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    players = [
        s for s in game_state.user_stats.values()
        if chat_id in s.get("played_in", set())
    ]
    if not players:
        return await update.message.reply_text("No scores recorded yet! Start via /game")

    # Sort by net score (wins - penalties), then by wins
    players.sort(key=lambda s: (s["wins"] - s.get("penalties", 0), s["wins"]), reverse=True)

    lines = ["🏆 <b>Dino Leaderboard</b>\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, p in enumerate(players[:10], 1):
        medal = medals[i - 1] if i <= 3 else f"{i}."
        penalties = p.get("penalties", 0)
        penalty_str = f"  ⚠️ -{penalties} penalty" if penalties > 0 else ""
        net = p["wins"] - penalties
        lines.append(
            f"{medal} <b>{p['name']}</b> — {p['wins']} win(s) · {p['led']} led"
            f"{penalty_str}\n"
            f"    <i>Net score: {net:+d}</i>"
        )
    await update.message.reply_html("\n".join(lines))


async def addword_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /addword <word>")
    word = context.args[0].lower().strip()
    if not word.isalpha():
        return await update.message.reply_text("Only letters allowed — no numbers or symbols.")
    if len(word) > 30:
        return await update.message.reply_text("Word too long (max 30 characters).")
    if word in config.WORD_LIST:
        return await update.message.reply_text(f"'{word.capitalize()}' is already in the word list!")
    if word in game_state.pending_words:
        return await update.message.reply_text("That word is already pending approval.")

    user = update.effective_user
    chat_id = update.effective_chat.id
    game_state.add_pending(word, user.first_name, user.id, chat_id)

    encoded = encode_word(word)
    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"app_{encoded}"),
        InlineKeyboardButton("❌ Reject",  callback_data=f"rej_{encoded}"),
    ]]
    try:
        await context.bot.send_message(
            chat_id=config.OWNER_ID,
            text=(
                f"📝 <b>Dino 2.0 Word Suggestion</b>\n"
                f"Word: <b>{word.capitalize()}</b>\n"
                f"From: {user.first_name} (id: <code>{user.id}</code>)"
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        await update.message.reply_text(f"✅ '{word.capitalize()}' sent for approval!")
    except Exception:
        await update.message.reply_text("⚠️ Could not reach the bot owner. Try again later.")


async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: list all pending word suggestions with approve/reject buttons."""
    if update.effective_user.id != config.OWNER_ID:
        return await update.message.reply_text("⛔ This command is only for the bot owner.")

    if not game_state.pending_words:
        return await update.message.reply_text("✅ No pending word suggestions right now.")

    await update.message.reply_html(
        f"📋 <b>Pending suggestions ({len(game_state.pending_words)})</b>"
    )
    for word, info in list(game_state.pending_words.items()):
        encoded = encode_word(word)
        keyboard = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"app_{encoded}"),
            InlineKeyboardButton("❌ Reject",  callback_data=f"rej_{encoded}"),
        ]]
        await update.message.reply_html(
            f"Word: <b>{word.capitalize()}</b>\n"
            f"Suggested by: {info['from_name']}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = game_state.active_games.get(chat_id)

    if game and game.get("is_active"):
        if user.id == game["leader_id"]:
            await update.message.reply_html(
                f"🦕 <b>{game['leader_name']}</b> is currently acting out the secret word!",
                reply_markup=leader_keyboard(),
            )
        else:
            await update.message.reply_html(
                f"🦕 <b>{game['leader_name']}</b> is explaining the word!\n"
                "Send a message in the chat to guess it!"
            )
    else:
        await update.message.reply_html(
            f"🦕 No active Dino game found here. Who wants to take the lead?",
            reply_markup=volunteer_keyboard(),
        )


# ── Dino 2.0 AI Core Handlers ──────────────────────────────────────────────────

async def ask_dino_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Text-only query channel to Dino 2.0 Engine"""
    if not ai_model:
        return await update.message.reply_text("🤖 Dino 2.0 engine is offline. DINO_API_KEY missing.")
    
    query = " ".join(context.args)
    if not query:
        return await update.message.reply_text("Please provide a prompt! Example: /ask Tell me a joke about dinosaurs.")
    
    status_msg = await update.message.reply_text("🤖 <i>Dino 2.0 is processing your thought...</i>", parse_mode="HTML")
    try:
        response = ai_model.generate_content(f"You are Dino 2.0, a witty, super intelligent dinosaur AI assistant. Answer this briefly and smartly: {query}")
        await status_msg.edit_text(response.text)
    except Exception as e:
        await status_msg.edit_text(f"❌ Error generating response: {str(e)}")


async def dino_multimodal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes images with /ask caption commands"""
    caption = update.message.caption or ""
    if not caption.startswith("/ask"):
        return 

    if not ai_model:
        return await update.message.reply_text("🤖 Dino 2.0 Vision engine configuration missing.")

    status_msg = await update.message.reply_text("🦕 <i>Dino 2.0 AI is analyzing your image...</i>", parse_mode="HTML")
    try:
        prompt_text = caption.replace("/ask", "").strip() or "Describe what you see in this image relative to the theme."
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        image = Image.open(io.BytesIO(photo_bytes))
        response = ai_model.generate_content([f"[Dino 2.0 Engine Vision Prompt]: {prompt_text}", image])
        await status_msg.edit_text(response.text)
    except Exception as e:
        await status_msg.edit_text(f"❌ Vision processing failed: {str(e)}")


# ── Callback buttons ───────────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    caller_id = query.from_user.id
    chat_id = query.message.chat_id

    # --- Volunteer or start new round ---
    if data in ("lead", "newgame"):
        existing = game_state.active_games.get(chat_id)
        if existing and existing.get("is_active"):
            await query.answer("A game is already running!", show_alert=True)
            return

        # Wipe out old trigger layout to minimize screen clutter
        try:
            await query.message.delete()
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass

        game_state.start_new_round(chat_id, caller_id, query.from_user.first_name)
        fire_auto_drop(chat_id, caller_id, context.bot)
        await query.answer()

        # Fire a brand new message down inside the active conversation flow
        new_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🦕 <b>{query.from_user.first_name}</b> became the Dino! Give hints in chat without saying the secret word!",
            parse_mode="HTML",
            reply_markup=leader_keyboard()
        )
        game_state.active_games[chat_id]["control_message_id"] = new_msg.message_id
        return

    # --- Word approval (owner only) ---
    if data.startswith("app_"):
        if caller_id != config.OWNER_ID:
            await query.answer("Only the bot owner can approve words.", show_alert=True)
            return
        word = decode_word(data[4:])
        config.add_new_word(word)
        game_state.remove_pending(word)
        await query.answer("Approved!")
        await query.edit_message_text(
            f"✅ Approved and added to prehistoric word list: <b>{word.capitalize()}</b>",
            parse_mode="HTML",
        )
        return

    if data.startswith("rej_"):
        if caller_id != config.OWNER_ID:
            await query.answer("Only the bot owner can reject words.", show_alert=True)
            return
        word = decode_word(data[4:])
        game_state.remove_pending(word)
        await query.answer("Rejected.")
        await query.edit_message_text(
            f"❌ Rejected: <b>{word.capitalize()}</b>",
            parse_mode="HTML",
        )
        return

    # --- Game controls (leader only) ---
    game = game_state.active_games.get(chat_id)

    if not game or not game["is_active"]:
        await query.answer("No active game right now.", show_alert=True)
        return

    if data in ("see", "write", "change"):
        if caller_id != game["leader_id"]:
            await query.answer("Only the active Dino can use this!", show_alert=True)
            return
        game_state.update_activity(chat_id)

    if data == "see":
        await query.answer(
            f"🦕 Your secret word is: {game['word'].upper()}",
            show_alert=True,
        )

    elif data == "write":
        try:
            await context.bot.send_message(
                chat_id=caller_id,
                text=f"🦕 Your secret word is: <b>{game['word'].upper()}</b>",
                parse_mode="HTML",
            )
            await query.answer("Word sent to your DM!")
        except Exception:
            await query.answer(
                "❌ I can't DM you. Send /start to me in private first, then try again.",
                show_alert=True,
            )

    elif data == "change":
        new_word = game_state.change_word(chat_id)
        await query.answer(f"🔄 New word assigned: {new_word.upper()}", show_alert=True)

    elif data == "drop":
        if caller_id != game["leader_id"] and caller_id != config.OWNER_ID:
            await query.answer("Only the Dino can drop their role.", show_alert=True)
            return
        game_state.drop_leader(chat_id)
        await query.answer("Lead dropped.")
        try:
            await query.message.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=chat_id,
            text="🦕 The Dino went back to the jungle. Who is next?",
            parse_mode="HTML",
            reply_markup=volunteer_keyboard(),
        )


# ── Message handler ────────────────────────────────────────────────────────────

async def check_guess_or_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = game_state.active_games.get(chat_id)
    if not game or not game["is_active"]:
        return

    sender = update.effective_user
    text = update.message.text.lower().strip()

    # ── Leader sent a message ──────────────────────────────────────────────────
    if sender.id == game["leader_id"]:
        game_state.update_activity(chat_id)

        if text == game["word"]:
            game_state.record_penalty(sender.id, sender.first_name, chat_id)
            await update.message.reply_html(
                f"⚠️ <b>{sender.first_name}</b>, you typed the secret word!\n"
                f"<b>-1 penalty point</b> added to your score."
            )
        return

    # ── Guesser message ───────────────────────────────────────────────────────
    if text != game["word"]:
        return

    # ── Correct guess! ────────────────────────────────────────────────────────
    word = game["word"]
    old_msg_id = game.get("control_message_id")
    
    game_state.drop_leader(chat_id)
    game_state.record_win(sender.id, sender.first_name, chat_id)

    # Clean up inline panel buttons on the finished round out-of-band
    if old_msg_id:
        try:
            await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=old_msg_id, reply_markup=None)
        except Exception:
            pass

    # 1. Victory announcement (Fresh message)
    await update.message.reply_html(f"🎉 <b>{sender.first_name}</b> caught the word: <b>{word.upper()}</b>!")

    # 2. Winner auto-becomes the next leader
    game_state.start_new_round(chat_id, sender.id, sender.first_name)
    fire_auto_drop(chat_id, sender.id, context.bot)

    # 3. Post a completely fresh game panel message right at the bottom of the group stream
    new_game_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🦕 <b>{sender.first_name}</b> is now the Dino! Use the controls below to check your secret word.",
        parse_mode="HTML",
        reply_markup=leader_keyboard()
    )
    game_state.active_games[chat_id]["control_message_id"] = new_game_msg.message_id
