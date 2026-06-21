import os

# Fetch secrets from environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

def load_words(filepath="word_list.txt"):
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            return [line.strip().lower() for line in file if line.strip()]
    except FileNotFoundError:
        return ["dinosaur", "fossil", "meteor"]

WORD_LIST = load_words()

def add_new_word(word, filepath="word_list.txt"):
    if word not in WORD_LIST:
        WORD_LIST.append(word)
        with open(filepath, "a", encoding="utf-8") as file:
            file.write(f"\n{word}")
