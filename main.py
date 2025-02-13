import os
import json
import random
import itertools
import datetime
import asyncio
import hashlib
import hmac
import urllib.parse
from typing import Tuple

from aiogram import Bot, Dispatcher, F
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.types.input_file import FSInputFile  # Импортируем FSInputFile для отправки файлов

# Импорт для веб-приложения
import uvicorn
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Замените на токен вашего бота
BOT_TOKEN = "7631229383:AAHc5p2MxjdC9huvVAOTrW2uG7z-QegWT9Y"
DATA_FILE = "data.json"

# Инициализация бота (aiogram)
bot = Bot(
    token=BOT_TOKEN,
    default_bot_properties=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Функция загрузки данных
def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            return {}

# Функция сохранения данных
def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

# Функция для создания/получения записи пользователя по его ID
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

# Функция генерации номера с расчетом стиля (цвет фона и текста)
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

# --------------------- Основные команды бота ---------------------

@dp.message(Command("start"))
async def start_cmd(message: Message) -> None:
    data = load_data()
    ensure_user(data, str(message.from_user.id),
                message.from_user.username or message.from_user.first_name)
    save_data(data)
    text = (
        "🎉 Добро пожаловать в Market коллекционных номеров! 🎉\n\n"
        "Чтобы войти, используйте команду /login <Ваш Telegram ID>.\n"
        "После этого бот отправит вам код подтверждения, который нужно ввести командой /verify <код>.\n"
        "Если вы уже вошли, можете использовать команды: /mint, /collection, /balance, /sell, /market, /buy, /participants, /exchange, /logout.\n"
        "Для установки аватарки отправьте фото с подписью: /setavatar\n"
        "\nДля автоматического входа на сайте воспользуйтесь ссылкой: "
        f"https://market-production-84b2.up.railway.app/auto_login?user_id={message.from_user.id}"
    )
    await message.answer(text)

@dp.message(Command("login"))
async def bot_login(message: Message) -> None:
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❗ Формат: /login <Ваш Telegram ID>")
        return
    user_id = parts[1]
    if user_id != str(message.from_user.id):
        await message.answer("❗ Вы можете войти только в свой аккаунт.")
        return
    data = load_data()
    user = ensure_user(data, user_id,
                       message.from_user.username or message.from_user.first_name)
    if user.get("logged_in"):
        await message.answer("Вы уже вошли!")
        return
    code = generate_login_code()
    expiry = (datetime.datetime.now() + datetime.timedelta(minutes=5)).timestamp()
    user["login_code"] = code
    user["code_expiry"] = expiry
    save_data(data)
    try:
        await bot.send_message(int(user_id), f"Ваш код для входа: {code}")
        await message.answer("Код подтверждения отправлен. Используйте команду /verify <код> для входа.")
    except Exception as e:
        await message.answer("Ошибка при отправке кода. Попробуйте позже.")
        print("Ошибка отправки кода:", e)

@dp.message(Command("verify"))
async def bot_verify(message: Message) -> None:
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❗ Формат: /verify <код>")
        return
    code = parts[1]
    user_id = str(message.from_user.id)
    data = load_data()
    user = data.get("users", {}).get(user_id)
    if not user:
        await message.answer("Пользователь не найден.")
        return
    if user.get("code_expiry", 0) < datetime.datetime.now().timestamp():
        await message.answer("Код устарел. Попробуйте /login снова.")
        return
    if user.get("login_code") != code:
        await message.answer("Неверный код.")
        return
    user["logged_in"] = True
    user["login_code"] = None
    user["code_expiry"] = None
    save_data(data)
    await message.answer("Вход выполнен успешно!")

@dp.message(Command("logout"))
async def bot_logout(message: Message) -> None:
    user_id = str(message.from_user.id)
    data = load_data()
    user = data.get("users", {}).get(user_id)
    if user:
        user["logged_in"] = False
        save_data(data)
    await message.answer("Вы вышли из аккаунта. Для входа используйте /login <Ваш Telegram ID>.")

# Обработчик для установки аватарки через фото.
@dp.message(F.photo)
async def handle_setavatar_photo(message: Message) -> None:
    if message.caption and message.caption.startswith("/setavatar"):
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
        data = load_data()
        user = ensure_user(data, str(message.from_user.id),
                           message.from_user.username or message.from_user.first_name)
        user["photo_url"] = file_url
        save_data(data)
        await message.answer("✅ Аватар обновлён!")

@dp.message(Command("mint"))
async def mint_number(message: Message) -> None:
    data = load_data()
    user = ensure_user(data, str(message.from_user.id),
                       message.from_user.username or message.from_user.first_name)
    today = datetime.date.today().isoformat()
    if user["last_activation_date"] != today:
        user["last_activation_date"] = today
        user["activation_count"] = 0
    if user["activation_count"] >= 3:
        await message.answer("😔 Вы исчерпали бесплатные активации на сегодня. Попробуйте завтра!")
        return
    user["activation_count"] += 1
    num, score, bg_color, text_color = generate_number()
    entry = {
        "token": num,
        "score": score,
        "timestamp": datetime.datetime.now().isoformat(),
        "bg_color": bg_color,
        "text_color": text_color
    }
    user["tokens"].append(entry)
    save_data(data)
    await message.answer(f"✨ Ваш новый коллекционный номер: {num}\n🔥 Оценка: {score}")

@dp.message(Command("collection"))
async def show_collection(message: Message) -> None:
    data = load_data()
    user = ensure_user(data, str(message.from_user.id))
    tokens = user.get("tokens", [])
    if not tokens:
        await message.answer("😕 У вас пока нет номеров. Используйте /mint для создания.")
        return
    msg = "🎨 " + "\n".join(f"{idx}. {t['token']} | Оценка: {t['score']}" for idx, t in enumerate(tokens, start=1))
    await message.answer(msg)

@dp.message(Command("balance"))
async def show_balance(message: Message) -> None:
    data = load_data()
    user = ensure_user(data, str(message.from_user.id))
    await message.answer(f"💎 Ваш баланс: {user.get('balance', 0)} 💎")

@dp.message(Command("sell"))
async def sell_number(message: Message) -> None:
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❗ Формат: /sell номер цена (например, /sell 2 500)")
        return
    try:
        index = int(parts[1]) - 1
        price = int(parts[2])
    except ValueError:
        await message.answer("❗ Проверьте формат номера и цены.")
        return
    data = load_data()
    user = ensure_user(data, str(message.from_user.id))
    tokens = user.get("tokens", [])
    if index < 0 or index >= len(tokens):
        await message.answer("❗ Неверный номер из вашей коллекции.")
        return
    item = tokens.pop(index)
    if "market" not in data:
        data["market"] = []
    listing = {
        "seller_id": str(message.from_user.id),
        "token": item,
        "price": price,
        "timestamp": datetime.datetime.now().isoformat()
    }
    data["market"].append(listing)
    save_data(data)
    await message.answer(f"🚀 Номер {item['token']} выставлен на продажу за {price} 💎!")

@dp.message(Command("market"))
async def show_market(message: Message) -> None:
    data = load_data()
    market = data.get("market", [])
    if not market:
        await message.answer("🌐 На маркетплейсе нет активных продаж.")
        return
    msg = "🌐 Номера на продаже:\n"
    for idx, listing in enumerate(market, start=1):
        seller_id = listing.get("seller_id")
        seller_name = data.get("users", {}).get(seller_id, {}).get("username", seller_id)
        token_info = listing["token"]
        msg += (f"{idx}. {token_info['token']} | Цена: {listing['price']} 💎 | "
                f"Продавец: {seller_name} | Оценка: {token_info['score']}\n")
    await message.answer(msg)

@dp.message(Command("buy"))
async def buy_number(message: Message) -> None:
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❗ Формат: /buy номер_листинга (например, /buy 1)")
        return
    try:
        listing_index = int(parts[1]) - 1
    except ValueError:
        await message.answer("❗ Неверный формат номера листинга.")
        return
    data = load_data()
    market = data.get("market", [])
    if listing_index < 0 or listing_index >= len(market):
        await message.answer("❗ Неверный номер листинга.")
        return
    listing = market[listing_index]
    seller_id = listing.get("seller_id")
    price = listing["price"]
    buyer_id = str(message.from_user.id)
    buyer = ensure_user(data, buyer_id)
    if buyer_id == seller_id:
        await message.answer("❗ Нельзя купить свой номер!")
        return
    if buyer.get("balance", 0) < price:
        await message.answer("😔 Недостаточно средств для покупки.")
        return
    buyer["balance"] -= price
    seller = data.get("users", {}).get(seller_id)
    if seller:
        seller["balance"] = seller.get("balance", 0) + price
    buyer.setdefault("tokens", []).append(listing["token"])
    market.pop(listing_index)
    save_data(data)
    await message.answer(f"🎉 Вы купили номер {listing['token']} за {price} 💎!\nНовый баланс: {buyer['balance']} 💎.")
    if seller:
        try:
            await bot.send_message(int(seller_id),
                                   f"Уведомление: Ваш номер {listing['token']} куплен за {price} 💎.")
        except Exception as e:
            print("Ошибка уведомления продавца:", e)

@dp.message(Command("participants"))
async def list_participants(message: Message) -> None:
    data = load_data()
    users = data.get("users", {})
    if not users:
        await message.answer("❗ Нет зарегистрированных участников.")
        return
    msg = "👥 Участники:\n"
    for uid, info in users.items():
        cnt = len(info.get("tokens", []))
        msg += f"{info.get('username', 'Неизвестный')} (ID: {uid}) — Баланс: {info.get('balance', 0)} 💎, номеров: {cnt}\n"
    await message.answer(msg)

@dp.message(Command("exchange"))
async def exchange_numbers(message: Message) -> None:
    parts = message.text.split()
    if len(parts) != 4:
        await message.answer("❗ Формат: /exchange <мой номер> <ID пользователя> <их номер>")
        return
    try:
        my_index = int(parts[1]) - 1
        target_uid = parts[2]
        target_index = int(parts[3]) - 1
    except ValueError:
        await message.answer("❗ Проверьте, что индексы и ID числа.")
        return
    data = load_data()
    initiator = ensure_user(data, str(message.from_user.id))
    if target_uid == str(message.from_user.id):
        await message.answer("❗ Нельзя обмениваться с самим собой!")
        return
    target = data.get("users", {}).get(target_uid)
    if not target:
        await message.answer("❗ Пользователь не найден.")
        return
    my_tokens = initiator.get("tokens", [])
    target_tokens = target.get("tokens", [])
    if my_index < 0 or my_index >= len(my_tokens):
        await message.answer("❗ Неверный номер вашего номера.")
        return
    if target_index < 0 or target_index >= len(target_tokens):
        await message.answer("❗ Неверный номер у пользователя.")
        return
    my_item = my_tokens.pop(my_index)
    target_item = target_tokens.pop(target_index)
    my_tokens.append(target_item)
    target_tokens.append(my_item)
    save_data(data)
    await message.answer(f"🎉 Обмен завершён!\nВы отдали номер {my_item['token']} и получили {target_item['token']}.")
    try:
        await bot.send_message(int(target_uid),
                               f"🔄 Пользователь {initiator.get('username', 'Неизвестный')} обменял с вами номера.\n"
                               f"Вы отдали {target_item['token']} и получили {my_item['token']}.")
    except Exception as e:
        print("Ошибка уведомления партнёра:", e)

# --------------------- Команды администратора ---------------------
# Только администраторы (определяемых в ADMIN_IDS) могут выполнять следующие команды.
ADMIN_IDS = {"1809630966", "7053559428"}  # Замените на реальные Telegram ID администраторов

@dp.message(Command("setbalance"))
async def set_balance(message: Message) -> None:
    if str(message.from_user.id) not in ADMIN_IDS:
        await message.answer("У вас нет доступа для выполнения этой команды.")
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❗ Формат: /setbalance <user_id> <новый баланс>")
        return
    target_user_id = parts[1]
    try:
        new_balance = int(parts[2])
    except ValueError:
        await message.answer("❗ Новый баланс должен быть числом.")
        return
    data = load_data()
    if "users" not in data or target_user_id not in data["users"]:
        await message.answer("❗ Пользователь не найден.")
        return
    user = data["users"][target_user_id]
    old_balance = user.get("balance", 0)
    user["balance"] = new_balance
    save_data(data)
    await message.answer(
        f"✅ Баланс пользователя {user.get('username', 'Неизвестный')} (ID: {target_user_id}) изменён с {old_balance} на {new_balance}."
    )

@dp.message(Command("listtokens"))
async def list_tokens_admin(message: Message) -> None:
    if str(message.from_user.id) not in ADMIN_IDS:
        await message.answer("У вас нет доступа для выполнения этой команды.")
        return
    args = message.get_args().split()
    if not args:
        await message.answer("Используйте: /listtokens <user_id>")
        return
    target_user_id = args[0]
    data = load_data()
    if "users" not in data or target_user_id not in data["users"]:
        await message.answer("❗ Пользователь не найден.")
        return
    user = data["users"][target_user_id]
    tokens = user.get("tokens", [])
    if not tokens:
        await message.answer("У пользователя нет коллекционных номеров.")
        return
    msg = f"Коллекционные номера пользователя {user.get('username', 'Неизвестный')} (ID: {target_user_id}):\n"
    for idx, token in enumerate(tokens, start=1):
        msg += f"{idx}. {token['token']} | Оценка: {token['score']}\n"
    await message.answer(msg)

@dp.message(Command("settoken"))
async def set_token_admin(message: Message) -> None:
    if str(message.from_user.id) not in ADMIN_IDS:
        await message.answer("У вас нет доступа для выполнения этой команды.")
        return
    parts = message.text.split()
    if len(parts) < 4:
        await message.answer("❗ Формат: /settoken <user_id> <номер_позиции> <новый_номер> [новая_оценка]")
        return
    target_user_id = parts[1]
    try:
        token_index = int(parts[2]) - 1  # 1-индексированный ввод
    except ValueError:
        await message.answer("❗ Проверьте, что номер позиции является числом.")
        return
    new_token_value = parts[3]
    new_score = None
    if len(parts) >= 5:
        try:
            new_score = int(parts[4])
        except ValueError:
            await message.answer("❗ Проверьте, что оценка является числом.")
            return
    data = load_data()
    if "users" not in data or target_user_id not in data["users"]:
        await message.answer("❗ Пользователь не найден.")
        return
    user = data["users"][target_user_id]
    tokens = user.get("tokens", [])
    if token_index < 0 or token_index >= len(tokens):
        await message.answer("❗ Неверный номер позиции токена.")
        return
    old_token = tokens[token_index].copy()
    tokens[token_index]["token"] = new_token_value
    if new_score is not None:
        tokens[token_index]["score"] = new_score
    save_data(data)
    await message.answer(
        f"✅ Токен для пользователя {user.get('username', 'Неизвестный')} (ID: {target_user_id}) изменён.\n"
        f"Было: {old_token}\nСтало: {tokens[token_index]}"
    )

@dp.message(Command("getdata"))
async def get_data_file(message: Message) -> None:
    # Ограничиваем выполнение команды только администраторам
    if str(message.from_user.id) not in ADMIN_IDS:
        await message.answer("У вас нет доступа для выполнения этой команды.")
        return

    if not os.path.exists(DATA_FILE):
        await message.answer("Файл data.json не найден.")
        return

    # Отправляем файл data.json как документ, используя FSInputFile
    document = FSInputFile(DATA_FILE)
    await message.answer_document(document=document, caption="Содержимое файла data.json")

# --------------------- Веб-приложение (FastAPI) ---------------------
app = FastAPI()

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")
templates.env.globals["enumerate"] = enumerate
templates.env.globals["get_rarity"] = get_rarity

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user_id = request.cookies.get("user_id")
    data = load_data()
    user = data.get("users", {}).get(user_id) if user_id else None
    market = data.get("market", [])
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "user_id": user_id,
        "market": market,
        "users": data.get("users", {})
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, user_id: str = Form(None)):
    if not user_id:
        user_id = request.cookies.get("user_id")
    if not user_id:
        return HTMLResponse("Ошибка: не найден Telegram ID.", status_code=400)
    data = load_data()
    user = ensure_user(data, user_id)
    if user.get("logged_in"):
        response = RedirectResponse(url=f"/profile/{user_id}", status_code=303)
        response.set_cookie("user_id", user_id, max_age=60*60*24*30, path="/")
        return response
    code = generate_login_code()
    expiry = (datetime.datetime.now() + datetime.timedelta(minutes=5)).timestamp()
    user["login_code"] = code
    user["code_expiry"] = expiry
    save_data(data)
    try:
        await bot.send_message(int(user_id), f"Ваш код для входа: {code}")
    except Exception as e:
        return HTMLResponse("Ошибка при отправке кода через Telegram.", status_code=500)
    return templates.TemplateResponse("verify.html", {"request": request, "user_id": user_id})

@app.post("/verify", response_class=HTMLResponse)
async def verify_post(request: Request, user_id: str = Form(...), code: str = Form(...)):
    data = load_data()
    user = data.get("users", {}).get(user_id)
    if not user:
        return HTMLResponse("Пользователь не найден.", status_code=404)
    if user.get("code_expiry", 0) < datetime.datetime.now().timestamp():
        return HTMLResponse("Код устарел. Повторите попытку входа.", status_code=400)
    if user.get("login_code") != code:
        return HTMLResponse("Неверный код.", status_code=400)
    user["logged_in"] = True
    user["login_code"] = None
    user["code_expiry"] = None
    save_data(data)
    response = RedirectResponse(url=f"/profile/{user_id}", status_code=303)
    response.set_cookie("user_id", user_id, max_age=60*60*24*30, path="/")
    return response

@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    user_id = request.cookies.get("user_id")
    if user_id:
        data = load_data()
        user = data.get("users", {}).get(user_id)
        if user:
            user["logged_in"] = False
            save_data(data)
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_id", path="/")
    return response

@app.get("/auto_login", response_class=HTMLResponse)
async def auto_login(request: Request, user_id: str):
    data = load_data()
    user = data.get("users", {}).get(user_id)
    if not user or not user.get("logged_in"):
        return RedirectResponse(url="/login", status_code=303)
    response = RedirectResponse(url=f"/profile/{user_id}", status_code=303)
    response.set_cookie("user_id", user_id, max_age=60*60*24*30, path="/")
    return response

@app.get("/profile/{user_id}", response_class=HTMLResponse)
async def profile(request: Request, user_id: str):
    data = load_data()
    user = data.get("users", {}).get(user_id)
    if not user:
        return HTMLResponse("Пользователь не найден.", status_code=404)
    current_user_id = request.cookies.get("user_id")
    is_owner = (current_user_id == user_id)
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user,
        "user_id": user_id,
        "is_owner": is_owner
    })

@app.get("/mint", response_class=HTMLResponse)
async def web_mint(request: Request):
    return templates.TemplateResponse("mint.html", {"request": request})

@app.post("/mint", response_class=HTMLResponse)
async def web_mint_post(request: Request, user_id: str = Form(None)):
    if not user_id:
        user_id = request.cookies.get("user_id")
    if not user_id:
        return HTMLResponse("Ошибка: не найден Telegram ID. Пожалуйста, войдите.", status_code=400)
    data = load_data()
    user = ensure_user(data, user_id)
    today = datetime.date.today().isoformat()
    if user["last_activation_date"] != today:
        user["last_activation_date"] = today
        user["activation_count"] = 0
    if user["activation_count"] >= 3:
        return templates.TemplateResponse("mint.html", {
            "request": request,
            "error": "Вы исчерпали бесплатные активации на сегодня. Попробуйте завтра!",
            "user_id": user_id
        })
    user["activation_count"] += 1
    num, score, bg_color, text_color = generate_number()
    entry = {
        "token": num,
        "score": score,
        "timestamp": datetime.datetime.now().isoformat(),
        "bg_color": bg_color,
        "text_color": text_color
    }
    user["tokens"].append(entry)
    save_data(data)
    return templates.TemplateResponse("profile.html", {"request": request, "user": user, "user_id": user_id})

@app.get("/sell", response_class=HTMLResponse)
async def web_sell(request: Request):
    return templates.TemplateResponse("sell.html", {"request": request})

@app.post("/sell", response_class=HTMLResponse)
async def web_sell_post(request: Request, user_id: str = Form(None), token_index: int = Form(...), price: int = Form(...)):
    if not user_id:
        user_id = request.cookies.get("user_id")
    if not user_id:
        return HTMLResponse("Ошибка: не найден Telegram ID. Пожалуйста, войдите.", status_code=400)
    data = load_data()
    user = data.get("users", {}).get(user_id)
    if not user:
        return HTMLResponse("Пользователь не найден.", status_code=404)
    tokens = user.get("tokens", [])
    if token_index < 1 or token_index > len(tokens):
        return HTMLResponse("Неверный номер из вашей коллекции.", status_code=400)
    token = tokens.pop(token_index - 1)
    if "market" not in data:
        data["market"] = []
    listing = {
        "seller_id": user_id,
        "token": token,
        "price": price,
        "timestamp": datetime.datetime.now().isoformat()
    }
    data["market"].append(listing)
    save_data(data)
    return templates.TemplateResponse("profile.html", {"request": request, "user": user, "user_id": user_id})

@app.get("/exchange", response_class=HTMLResponse)
async def web_exchange(request: Request):
    return templates.TemplateResponse("exchange.html", {"request": request})

@app.post("/exchange", response_class=HTMLResponse)
async def web_exchange_post(request: Request, user_id: str = Form(None), my_index: int = Form(...), target_id: str = Form(...), target_index: int = Form(...)):
    if not user_id:
        user_id = request.cookies.get("user_id")
    if not user_id:
        return HTMLResponse("Ошибка: не найден Telegram ID. Пожалуйста, войдите.", status_code=400)
    data = load_data()
    initiator = data.get("users", {}).get(user_id)
    target = data.get("users", {}).get(target_id)
    if not initiator or not target:
        return HTMLResponse("Один из пользователей не найден.", status_code=404)
    my_tokens = initiator.get("tokens", [])
    target_tokens = target.get("tokens", [])
    if my_index < 1 or my_index > len(my_tokens) or target_index < 1 or target_index > len(target_tokens):
        return HTMLResponse("Неверный номер у одного из пользователей.", status_code=400)
    my_token = my_tokens.pop(my_index - 1)
    target_token = target_tokens.pop(target_index - 1)
    my_tokens.append(target_token)
    target_tokens.append(my_token)
    save_data(data)
    return templates.TemplateResponse("profile.html", {"request": request, "user": initiator, "user_id": user_id})

@app.get("/participants", response_class=HTMLResponse)
async def web_participants(request: Request):
    data = load_data()
    users = data.get("users", {})
    return templates.TemplateResponse("participants.html", {"request": request, "users": users})

@app.get("/market", response_class=HTMLResponse)
async def web_market(request: Request):
    data = load_data()
    market = data.get("market", [])
    return templates.TemplateResponse("market.html", {
        "request": request,
        "market": market,
        "users": data.get("users", {}),
        "buyer_id": request.cookies.get("user_id")
    })

@app.post("/buy/{listing_index}")
async def web_buy(request: Request, listing_index: int, buyer_id: str = Form(None)):
    if not buyer_id:
        buyer_id = request.cookies.get("user_id")
    if not buyer_id:
        return HTMLResponse("Ошибка: не найден Telegram ID. Пожалуйста, войдите.", status_code=400)
    data = load_data()
    market = data.get("market", [])
    if listing_index < 0 or listing_index >= len(market):
        return HTMLResponse("Неверный номер листинга.", status_code=400)
    listing = market[listing_index]
    seller_id = listing.get("seller_id")
    price = listing["price"]
    buyer = data.get("users", {}).get(buyer_id)
    if not buyer:
        return HTMLResponse("Покупатель не найден.", status_code=404)
    if buyer.get("balance", 0) < price:
        return HTMLResponse("Недостаточно средств.", status_code=400)
    buyer["balance"] -= price
    seller = data.get("users", {}).get(seller_id)
    if seller:
        seller["balance"] = seller.get("balance", 0) + price
    buyer.setdefault("tokens", []).append(listing["token"])
    market.pop(listing_index)
    save_data(data)
    return templates.TemplateResponse("profile.html", {"request": request, "user": buyer, "user_id": buyer_id})

# --------------------- Запуск бота и веб-сервера ---------------------
async def main():
    bot_task = asyncio.create_task(dp.start_polling(bot))
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    web_task = asyncio.create_task(server.serve())
    await asyncio.gather(bot_task, web_task)

if __name__ == "__main__":
    asyncio.run(main())
