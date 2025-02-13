# utils.py
import os
import json
import random
import itertools
import datetime
from typing import Tuple

DATA_FILE = "data.json"

def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            return {}

def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

def ensure_user(data: dict, user_id: str, username: str = "Unknown", photo_url: str = None) -> dict:
    today = datetime.date.today().isoformat()
    if "users" not in data:
        data["users"] = {}
    if user_id not in data["users"]:
        data["users"][user_id] = {
            "last_activation_date": today,
            "activation_count": 0,
            "tokens": [],
            "balance": 1000,
            "username": username,
            "photo_url": photo_url,
            "logged_in": False,
            "login_code": None,
            "code_expiry": None
        }
    return data["users"][user_id]

def beauty_score(num_str: str) -> int:
    zeros = num_str.count("0")
    max_repeats = max(len(list(group)) for _, group in itertools.groupby(num_str))
    bonus = 6 - len(num_str)
    return zeros + max_repeats + bonus

def generate_number() -> Tuple[str, int, str, str]:
    possible_text_colors = ["#1abc9c", "#2ecc71", "#3498db", "#9b59b6", "#34495e"]
    possible_bg_colors = ["#e74c3c", "#e67e22", "#f1c40f", "#16a085", "#27ae60"]

    num, score = None, None
    while True:
        length = random.choices([3, 4, 5, 6], weights=[1, 2, 3, 4])[0]
        candidate = "".join(random.choices("0123456789", k=length))
        score = beauty_score(candidate)
        if random.random() < 1 / (score + 1):
            num = candidate
            break

    text_color = random.choice(possible_text_colors)
    bg_color = random.choice(possible_bg_colors)
    return num, score, bg_color, text_color

def generate_login_code() -> str:
    return str(random.randint(100000, 999999))

def get_rarity(score: int) -> str:
    if score > 12:
        return "0,5%"
    elif score > 8:
        return "1%"
    else:
        return "2%"
