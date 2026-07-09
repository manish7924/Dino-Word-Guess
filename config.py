import os

# Fetch secrets from environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
CROCO_API_KEY = os.environ.get("CROCO_API_KEY") # Added for Croco 2.0 Multimodal features

def load_words(filepath="word_list.txt"):
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            return [line.strip().lower() for line in file if line.strip()]
    except FileNotFoundError:
        # Rebranded default fallbacks
        return ["crocodile", "swamp", "reptile", "predator"]

WORD_LIST = load_words()

def add_new_word(word, filepath="word_list.txt"):
    if word not in WORD_LIST:
        WORD_LIST.append(word)
        with open(filepath, "a", encoding="utf-8") as file:
            file.write(f"\n{word}")
