import random
from config import WORD_LIST

active_games = {}
user_stats = {}
pending_words = {}   # {word: {"from_name": str, "from_id": int, "chat_id": int}}


def get_random_word():
    return random.choice(WORD_LIST)


def init_user(user_id, name):
    if user_id not in user_stats:
        user_stats[user_id] = {"name": name, "wins": 0, "led": 0, "played_in": set()}


def start_new_round(chat_id, user_id, user_name):
    init_user(user_id, user_name)
    user_stats[user_id]["led"] += 1
    user_stats[user_id]["played_in"].add(chat_id)
    active_games[chat_id] = {
        "leader_id": user_id,
        "leader_name": user_name,
        "word": get_random_word(),
        "is_active": True,
    }


def change_word(chat_id):
    if chat_id in active_games and active_games[chat_id]["is_active"]:
        active_games[chat_id]["word"] = get_random_word()
        return active_games[chat_id]["word"]
    return None


def drop_leader(chat_id):
    if chat_id in active_games:
        active_games[chat_id]["is_active"] = False


def record_win(user_id, name, chat_id):
    init_user(user_id, name)
    user_stats[user_id]["wins"] += 1
    user_stats[user_id]["played_in"].add(chat_id)


def add_pending(word, from_name, from_id, chat_id):
    pending_words[word] = {
        "from_name": from_name,
        "from_id": from_id,
        "chat_id": chat_id,
    }


def remove_pending(word):
    return pending_words.pop(word, None)
