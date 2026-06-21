import random
from config import WORD_LIST

active_games = {}
user_stats = {}

def get_random_word():
    return random.choice(WORD_LIST)

def init_user(user_id, name):
    if user_id not in user_stats:
        user_stats[user_id] = {"name": name, "score": 0, "played_in": set()}

def start_new_round(chat_id, user_id, user_name):
    init_user(user_id, user_name)
    user_stats[user_id]["played_in"].add(chat_id)
    active_games[chat_id] = {"leader_id": user_id, "leader_name": user_name, "word": get_random_word(), "is_active": True}

def drop_leader(chat_id):
    if chat_id in active_games:
        active_games[chat_id]["is_active"] = False
