import asyncio
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import game_state, config

# How long (seconds) before the bot auto-drops an idle leader
AUTO_DROP_SECONDS = 120  # 2 minutes

HELP_TEXT = (
    "🦕 <b>Dino Word Guess</b>\n\n"
    "<b>How to play:</b>\n"
    "1️⃣ /game — volunteer as leader by tapping the button.\n"
    "2️⃣ Leader uses <b>See word</b> 🔍 to view the secret word.\n"
    "3️⃣ Give hints in chat — <b>don't type the word itself!</b>\n"
    "4️⃣ Everyone else guesses by sending messages.\n"
    "5️⃣ First correct guess wins a point and becomes the next leader!\n\n"
    "<b>Scoring:</b>\n"
    "✅ Correct guess → +1 point for the guesser\n"
    "⚠️ Leader types the secret word → -1 penalty for the leader\n\n"
    "<b>Commands:</b>\n"
    "/game — start or check the current round\n"
    "/scores — leaderboard for this chat\n"
    "/addword &lt;word&gt; — suggest a new word\n"
    "/pending — (owner) review pending word suggestions\n"
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
        InlineKeyboardButton("🎮 I want to be a leader!", callback_data="lead"),
    ]])


def new_game_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🎲 Start new game!", callback_data="newgame"),
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
        game_state.drop_leader(chat_id)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⏰ <b>{leader_name}</b> was idle too long — lead dropped!\n"
                    "🦕 Who wants to take over?"
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

    # Sort by net score (wins - penalties), then by wins
    players.sort(key=lambda s: (s["wins"] - s.get("penalties", 0), s["wins"]), reverse=True)

    lines = ["🏆 <b>Leaderboard</b>\n"]
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
                f"📝 <b>New word suggestion</b>\n"
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
                f"🦕 <b>{game['leader_name']}</b> is explaining the word!",
                reply_markup=leader_keyboard(),
            )
        else:
            await update.message.reply_html(
                f"🦕 <b>{game['leader_name']}</b> is explaining the word!\n"
                "Send a message in the chat to guess it!"
            )
    else:
        await update.message.reply_html(
            f"🦕 <b>{user.first_name}</b> refused to lead!\n"
            "Will someone else step up?",
            reply_markup=volunteer_keyboard(),
        )


# ── Callback buttons ───────────────────────────────────────────────────────────

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
        fire_auto_drop(chat_id, caller_id, context.bot)
        await query.answer()
        await query.edit_message_text(
            f"🦕 <b>{query.from_user.first_name}</b> is explaining the word!",
            parse_mode="HTML",
            reply_markup=leader_keyboard(),
        )
        return

    # --- Start new game button (shown after a win) ---
    if data == "newgame":
        existing = game_state.active_games.get(chat_id)
        if existing and existing.get("is_active"):
            await query.answer("Game already started!", show_alert=False)
            return
        game_state.start_new_round(chat_id, caller_id, query.from_user.first_name)
        fire_auto_drop(chat_id, caller_id, context.bot)
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🦕 <b>{query.from_user.first_name}</b> is explaining the word!",
            parse_mode="HTML",
            reply_markup=leader_keyboard(),
        )
        return

    # --- Word approval (owner only) ---
    if data.startswith("app_"):
        if caller_id != config.OWNER_ID:
            await query.answer("Only the bot owner can approve words.", show_alert=True)
            return
        word = decode_word(data[4:])
        config.add_new_word(word)
        game_state.remove_pending(word)
        await query.answer(f"✅ Approved!")
        await query.edit_message_text(
            f"✅ Approved and added to word list: <b>{word.capitalize()}</b>",
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
            await query.answer("Only the leader can use this!", show_alert=True)
            return
        # Refresh idle timer on any leader button press
        game_state.update_activity(chat_id)

    if data == "see":
        await query.answer(
            f"🦕 Your word is: {game['word'].capitalize()}",
            show_alert=True,
        )

    elif data == "write":
        try:
            await context.bot.send_message(
                chat_id=caller_id,
                text=f"🦕 Your secret word is: <b>{game['word'].capitalize()}</b>",
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
        await query.answer(f"🔄 New word: {new_word.capitalize()}", show_alert=True)

    elif data == "drop":
        if caller_id != game["leader_id"] and caller_id != config.OWNER_ID:
            await query.answer("Only the leader can drop their role.", show_alert=True)
            return
        leader_name = game["leader_name"]
        game_state.drop_leader(chat_id)
        await query.answer("Lead dropped.")
        await query.edit_message_text(
            f"🦕 <b>{leader_name}</b> refused to lead!\nWill someone else step up?",
            parse_mode="HTML",
            reply_markup=volunteer_keyboard(),
        )


# ── Message handler ────────────────────────────────────────────────────────────

async def check_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = game_state.active_games.get(chat_id)
    if not game or not game["is_active"]:
        return

    sender = update.effective_user
    text = update.message.text.lower().strip()

    # ── Leader sent a message ──────────────────────────────────────────────────
    if sender.id == game["leader_id"]:
        game_state.update_activity(chat_id)  # any leader message resets idle timer

        if text == game["word"]:
            # Leader typed the secret word — penalty!
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
    game_state.drop_leader(chat_id)
    game_state.record_win(sender.id, sender.first_name, chat_id)

    # 1. Victory announcement
    await update.message.reply_html(
        f"🎉 <b>{sender.first_name}</b> found the word! <b>{word}</b>",
        reply_markup=new_game_keyboard(),
    )

    # 2. Winner auto-becomes the new leader
    game_state.start_new_round(chat_id, sender.id, sender.first_name)
    fire_auto_drop(chat_id, sender.id, context.bot)

    # 3. Post leader controls
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🦕 <b>{sender.first_name}</b> is explaining the word!",
        parse_mode="HTML",
        reply_markup=leader_keyboard(),
    )
