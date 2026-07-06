from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import game_state, config

HELP_TEXT = (
    "🦕 <b>Dino Word Guess</b>\n\n"
    "<b>How to play:</b>\n"
    "1. Use /game — someone volunteers as leader by tapping the button.\n"
    "2. Leader taps 🔍 <b>See word</b> to view the secret word (popup).\n"
    "3. Tap ✏️ <b>Write word</b> to get the word sent to your private DM.\n"
    "4. Tap 🔄 <b>Change word</b> to get a new random word.\n"
    "5. Everyone else guesses by sending messages in the chat.\n"
    "6. First correct guess wins a point!\n\n"
    "<b>Commands:</b>\n"
    "/game — start a round (volunteer as leader)\n"
    "/scores — leaderboard for this chat\n"
    "/addword &lt;word&gt; — suggest a new word\n"
    "/pending — (owner) view pending word suggestions\n\n"
    "⚠️ <i>In groups, make sure the bot's Privacy Mode is OFF in BotFather.</i>"
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
        InlineKeyboardButton("🎮 I want to be a leader!", callback_data="lead"),
    ]])


def encode_word(word):
    return word.replace("_", "\u2019")


def decode_word(encoded):
    return encoded.replace("\u2019", "_")


# ── Commands ──────────────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "👋 Hi! I'm <b>Dino Word Guess Bot</b> 🦕\n\n" + HELP_TEXT
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
        return await update.message.reply_text("No scores yet — start a game with /game!")
    players.sort(key=lambda s: s["wins"], reverse=True)
    lines = ["🏆 <b>Leaderboard</b>\n"]
    for i, p in enumerate(players[:10], 1):
        lines.append(f"{i}. {p['name']} — {p['wins']} win(s), {p['led']} round(s) led")
    await update.message.reply_html("\n".join(lines))


async def addword_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /addword <word>")
    word = context.args[0].lower()
    if len(word) > 30:
        return await update.message.reply_text("Word too long (max 30 characters).")
    if word in config.WORD_LIST:
        return await update.message.reply_text("That word is already in the list!")
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
                f"📝 New word suggestion\n"
                f"Word: <b>{word}</b>\n"
                f"From: {user.first_name} (id: <code>{user.id}</code>)"
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        await update.message.reply_text("✅ Sent for approval!")
    except Exception:
        await update.message.reply_text("⚠️ Could not reach the bot owner. Try again later.")


async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: list all pending word suggestions with approve/reject buttons."""
    if update.effective_user.id != config.OWNER_ID:
        return await update.message.reply_text("This command is only for the bot owner.")

    if not game_state.pending_words:
        return await update.message.reply_text("✅ No pending word suggestions.")

    await update.message.reply_text(
        f"📋 <b>Pending word suggestions ({len(game_state.pending_words)})</b>",
        parse_mode="HTML",
    )

    for word, info in list(game_state.pending_words.items()):
        encoded = encode_word(word)
        keyboard = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"app_{encoded}"),
            InlineKeyboardButton("❌ Reject",  callback_data=f"rej_{encoded}"),
        ]]
        await update.message.reply_html(
            f"Word: <b>{word}</b>\n"
            f"Suggested by: {info['from_name']}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = game_state.active_games.get(chat_id)

    if game and game.get("is_active"):
        # Game already running
        if user.id == game["leader_id"]:
            await update.message.reply_html(
                f"🦕 <b>{game['leader_name']}</b> is explaining the word!",
                reply_markup=leader_keyboard(),
            )
        else:
            await update.message.reply_html(
                f"🦕 <b>{game['leader_name']}</b> is explaining the word!\n"
                "Send a message to guess it!"
            )
    else:
        # No active game — ask for a volunteer
        await update.message.reply_html(
            f"🦕 <b>{user.first_name}</b> refused to lead!",
            reply_markup=volunteer_keyboard(),
        )


# ── Callback buttons ──────────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    caller_id = query.from_user.id
    chat_id = query.message.chat_id

    # --- Volunteer to lead ---
    if data == "lead":
        existing = game_state.active_games.get(chat_id)
        if existing and existing.get("is_active"):
            await query.answer(
                f"A game is already running! {existing['leader_name']} is leading.",
                show_alert=True,
            )
            return
        game_state.start_new_round(chat_id, caller_id, query.from_user.first_name)
        await query.answer()
        await query.edit_message_text(
            f"🦕 <b>{query.from_user.first_name}</b> is explaining the word!",
            parse_mode="HTML",
            reply_markup=leader_keyboard(),
        )
        return

    # --- Word approval (owner only, works from DM or group) ---
    if data.startswith("app_"):
        if caller_id != config.OWNER_ID:
            await query.answer("Only the bot owner can approve words.", show_alert=True)
            return
        word = decode_word(data[4:])
        config.add_new_word(word)
        game_state.remove_pending(word)
        await query.answer("Approved!")
        await query.edit_message_reply_markup(reply_markup=None)
        await query.edit_message_text(f"✅ Approved and added: <b>{word}</b>", parse_mode="HTML")
        return

    if data.startswith("rej_"):
        if caller_id != config.OWNER_ID:
            await query.answer("Only the bot owner can reject words.", show_alert=True)
            return
        word = decode_word(data[4:])
        game_state.remove_pending(word)
        await query.answer("Rejected.")
        await query.edit_message_reply_markup(reply_markup=None)
        await query.edit_message_text(f"❌ Rejected: <b>{word}</b>", parse_mode="HTML")
        return

    # --- Game controls (leader only) ---
    game = game_state.active_games.get(chat_id)

    if not game or not game["is_active"]:
        await query.answer("No active game.", show_alert=True)
        return

    if data in ("see", "write", "change"):
        if caller_id != game["leader_id"]:
            await query.answer("Only the leader can use this.", show_alert=True)
            return

    if data == "see":
        await query.answer(
            f"🦕 Your word is: {game['word'].upper()}",
            show_alert=True,
        )

    elif data == "write":
        try:
            await context.bot.send_message(
                chat_id=caller_id,
                text=f"🦕 Your secret word is: <b>{game['word'].upper()}</b>",
                parse_mode="HTML",
            )
            await query.answer("Word sent to your private chat!")
        except Exception:
            await query.answer(
                "❌ I can't DM you. Send /start to me in private first, then try again.",
                show_alert=True,
            )

    elif data == "change":
        new_word = game_state.change_word(chat_id)
        await query.answer(f"🔄 New word: {new_word.upper()}", show_alert=True)

    elif data == "drop":
        if caller_id != game["leader_id"] and caller_id != config.OWNER_ID:
            await query.answer("Only the leader can drop their role.", show_alert=True)
            return
        leader_name = game["leader_name"]
        game_state.drop_leader(chat_id)
        await query.answer("Lead dropped.")
        await query.edit_message_text(
            f"🦕 <b>{leader_name}</b> refused to lead!",
            parse_mode="HTML",
            reply_markup=volunteer_keyboard(),
        )


# ── Message handler ───────────────────────────────────────────────────────────

async def check_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = game_state.active_games.get(update.effective_chat.id)
    if not game or not game["is_active"]:
        return
    if update.effective_user.id == game["leader_id"]:
        return
    if update.message.text.lower().strip() == game["word"]:
        guesser = update.effective_user
        word = game["word"]
        game_state.drop_leader(update.effective_chat.id)
        game_state.record_win(guesser.id, guesser.first_name, update.effective_chat.id)
        await update.message.reply_html(
            f"🎉 <b>{guesser.first_name}</b> guessed it! "
            f"The word was <b>{word.upper()}</b>.\n\n"
            "Use /game to start a new round!",
            reply_markup=volunteer_keyboard(),
        )
