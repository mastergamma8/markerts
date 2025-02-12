import os
import random
import itertools
import datetime
import asyncio
from typing import Tuple
import ssl  # Импорт модуля ssl

import asyncpg

from aiogram import Bot, Dispatcher, F
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

import uvicorn
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Получите переменные окружения (на локальном ПК можно задать их в файле .env или напрямую)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7631229383:AAHc5p2MxjdC9huvVAOTrW2uG7z-QegWT9Y")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:1888@localhost:5432/macuser")

# Инициализация бота (aiogram)
bot = Bot(
    token=BOT_TOKEN,
    default_bot_properties=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Глобальный пул соединений
db_pool = None

# ====================== Инициализация базы данных ======================
async def init_db():
    global db_pool
    # Если в строке подключения не используется localhost, предполагаем удалённую базу (например, Railway)
    # и создаём SSL контекст для зашифрованного соединения.
    ssl_context = None
    if "localhost" not in DATABASE_URL:
        ssl_context = ssl.create_default_context()
        # Отключаем проверку имени сервера и сертификата,
        # чтобы избежать ошибок при использовании самоподписанных сертификатов.
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    db_pool = await asyncpg.create_pool(DATABASE_URL, ssl=ssl_context)
    async with db_pool.acquire() as connection:
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT,
                photo_url TEXT,
                last_activation_date TEXT,
                activation_count INTEGER,
                balance INTEGER,
                logged_in INTEGER,
                login_code TEXT,
                code_expiry DOUBLE PRECISION
            )
        """)
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                id SERIAL PRIMARY KEY,
                user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
                token TEXT,
                score INTEGER,
                timestamp TEXT,
                bg_color TEXT,
                text_color TEXT
            )
        """)
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS market (
                id SERIAL PRIMARY KEY,
                seller_id TEXT REFERENCES users(id) ON DELETE CASCADE,
                token TEXT,
                score INTEGER,
                timestamp TEXT,
                bg_color TEXT,
                text_color TEXT,
                price INTEGER
            )
        """)
except Exception as e:
        print(f"Ошибка при подключении к базе данных: {e}")
        raise

# ====================== Функции для работы с базой данных ======================
async def get_user(user_id: str):
    async with db_pool.acquire() as connection:
        row = await connection.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return dict(row) if row else None

async def get_or_create_user(user_id: str, username: str = "Unknown", photo_url: str = None):
    user = await get_user(user_id)
    if not user:
        today = datetime.date.today().isoformat()
        async with db_pool.acquire() as connection:
            await connection.execute("""
                INSERT INTO users (id, username, photo_url, last_activation_date, activation_count, balance, logged_in)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, user_id, username, photo_url, today, 0, 1000, 0)
        user = await get_user(user_id)
    return user

async def update_user(user_id: str, **fields):
    if not fields:
        return
    set_clause = ", ".join([f"{k} = ${i+2}" for i, k in enumerate(fields.keys())])
    values = list(fields.values())
    async with db_pool.acquire() as connection:
        await connection.execute(f"UPDATE users SET {set_clause} WHERE id = $1", user_id, *values)

async def add_token(user_id: str, token: str, score: int, timestamp: str, bg_color: str, text_color: str):
    async with db_pool.acquire() as connection:
        await connection.execute("""
            INSERT INTO tokens (user_id, token, score, timestamp, bg_color, text_color)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, user_id, token, score, timestamp, bg_color, text_color)

async def get_tokens(user_id: str):
    async with db_pool.acquire() as connection:
        rows = await connection.fetch("SELECT * FROM tokens WHERE user_id = $1 ORDER BY id", user_id)
        return [dict(row) for row in rows]

async def remove_token(token_id: int):
    async with db_pool.acquire() as connection:
        await connection.execute("DELETE FROM tokens WHERE id = $1", token_id)

async def add_market_listing(seller_id: str, token: str, score: int, timestamp: str, bg_color: str, text_color: str, price: int):
    async with db_pool.acquire() as connection:
        await connection.execute("""
            INSERT INTO market (seller_id, token, score, timestamp, bg_color, text_color, price)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, seller_id, token, score, timestamp, bg_color, text_color, price)

async def get_market_listings():
    async with db_pool.acquire() as connection:
        rows = await connection.fetch("SELECT * FROM market ORDER BY id")
        return [dict(row) for row in rows]

async def remove_market_listing(listing_id: int):
    async with db_pool.acquire() as connection:
        await connection.execute("DELETE FROM market WHERE id = $1", listing_id)

async def update_token_owner(token_id: int, new_owner: str):
    async with db_pool.acquire() as connection:
        await connection.execute("UPDATE tokens SET user_id = $1 WHERE id = $2", new_owner, token_id)

async def get_token_by_index(user_id: str, index: int):
    async with db_pool.acquire() as connection:
        row = await connection.fetchrow("SELECT * FROM tokens WHERE user_id = $1 ORDER BY id LIMIT 1 OFFSET $2", user_id, index)
        return dict(row) if row else None

# ====================== Функции для генерации номера ======================
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

# ====================== Обработчики команд бота ======================
@dp.message(Command("start"))
async def start_cmd(message: Message) -> None:
    user_id = str(message.from_user.id)
    await get_or_create_user(user_id, message.from_user.username or message.from_user.first_name)
    text = (
        "🎉 Добро пожаловать в Market коллекционных номеров! 🎉\n\n"
        "Чтобы войти, используйте команду /login <Ваш Telegram ID>.\n"
        "После этого бот отправит вам код подтверждения, который нужно ввести командой /verify <код>.\n"
        "Если вы уже вошли, можете использовать команды: /mint, /collection, /balance, /sell, /market, /buy, /participants, /exchange, /logout.\n"
        "Для установки аватарки отправьте фото с подписью: /setavatar\n"
        "\nДля автоматического входа на сайте воспользуйтесь ссылкой: "
        f"https://your-domain.example/auto_login?user_id={user_id}"
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
    user = await get_or_create_user(user_id, message.from_user.username or message.from_user.first_name)
    if user.get("logged_in"):
        await message.answer("Вы уже вошли!")
        return
    code = generate_login_code()
    expiry = (datetime.datetime.now() + datetime.timedelta(minutes=5)).timestamp()
    await update_user(user_id, login_code=code, code_expiry=expiry)
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
    user = await get_user(user_id)
    if not user:
        await message.answer("Пользователь не найден.")
        return
    if user.get("code_expiry", 0) < datetime.datetime.now().timestamp():
        await message.answer("Код устарел. Попробуйте /login снова.")
        return
    if user.get("login_code") != code:
        await message.answer("Неверный код.")
        return
    await update_user(user_id, logged_in=1, login_code=None, code_expiry=None)
    await message.answer("Вход выполнен успешно!")

@dp.message(Command("logout"))
async def bot_logout(message: Message) -> None:
    user_id = str(message.from_user.id)
    await update_user(user_id, logged_in=0)
    await message.answer("Вы вышли из аккаунта. Для входа используйте /login <Ваш Telegram ID>.")

@dp.message(F.photo)
async def handle_setavatar_photo(message: Message) -> None:
    if message.caption and message.caption.startswith("/setavatar"):
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
        user_id = str(message.from_user.id)
        await update_user(user_id, photo_url=file_url)
        await message.answer("✅ Аватар обновлён!")

@dp.message(Command("mint"))
async def mint_number(message: Message) -> None:
    user_id = str(message.from_user.id)
    user = await get_or_create_user(user_id, message.from_user.username or message.from_user.first_name)
    today = datetime.date.today().isoformat()
    if user.get("last_activation_date") != today:
        await update_user(user_id, last_activation_date=today, activation_count=0)
    if user.get("activation_count", 0) >= 3:
        await message.answer("😔 Вы исчерпали бесплатные активации на сегодня. Попробуйте завтра!")
        return
    new_count = user.get("activation_count", 0) + 1
    await update_user(user_id, activation_count=new_count)
    num, score, bg_color, text_color = generate_number()
    timestamp = datetime.datetime.now().isoformat()
    await add_token(user_id, num, score, timestamp, bg_color, text_color)
    await message.answer(f"✨ Ваш новый коллекционный номер: {num}\n🔥 Оценка: {score}")

@dp.message(Command("collection"))
async def show_collection(message: Message) -> None:
    user_id = str(message.from_user.id)
    tokens = await get_tokens(user_id)
    if not tokens:
        await message.answer("😕 У вас пока нет номеров. Используйте /mint для создания.")
        return
    msg = "🎨 Коллекция номеров:\n"
    for idx, token in enumerate(tokens, start=1):
        msg += f"{idx}. {token['token']} | Оценка: {token['score']}\n"
    await message.answer(msg)

@dp.message(Command("balance"))
async def show_balance(message: Message) -> None:
    user_id = str(message.from_user.id)
    user = await get_user(user_id)
    balance = user.get("balance", 0) if user else 0
    await message.answer(f"💎 Ваш баланс: {balance} 💎")

@dp.message(Command("sell"))
async def sell_number(message: Message) -> None:
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❗ Формат: /sell <номер в коллекции> <цена> (например, /sell 2 500)")
        return
    try:
        index = int(parts[1]) - 1
        price = int(parts[2])
    except ValueError:
        await message.answer("❗ Проверьте формат номера и цены.")
        return
    user_id = str(message.from_user.id)
    tokens = await get_tokens(user_id)
    if index < 0 or index >= len(tokens):
        await message.answer("❗ Неверный номер из вашей коллекции.")
        return
    token_entry = tokens[index]
    await remove_token(token_entry["id"])
    listing_time = datetime.datetime.now().isoformat()
    await add_market_listing(user_id, token_entry["token"], token_entry["score"],
                             listing_time, token_entry["bg_color"], token_entry["text_color"], price)
    await message.answer(f"🚀 Номер {token_entry['token']} выставлен на продажу за {price} 💎!")

@dp.message(Command("market"))
async def show_market(message: Message) -> None:
    listings = await get_market_listings()
    if not listings:
        await message.answer("🌐 На маркетплейсе нет активных продаж.")
        return
    msg = "🌐 Номера на продаже:\n"
    for idx, listing in enumerate(listings, start=1):
        seller = await get_user(listing["seller_id"])
        seller_name = seller.get("username", listing["seller_id"]) if seller else listing["seller_id"]
        msg += f"{idx}. {listing['token']} | Цена: {listing['price']} 💎 | Продавец: {seller_name} | Оценка: {listing['score']}\n"
    await message.answer(msg)

@dp.message(Command("buy"))
async def buy_number(message: Message) -> None:
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❗ Формат: /buy <номер листинга> (например, /buy 1)")
        return
    try:
        listing_index = int(parts[1]) - 1
    except ValueError:
        await message.answer("❗ Неверный формат номера листинга.")
        return
    listings = await get_market_listings()
    if listing_index < 0 or listing_index >= len(listings):
        await message.answer("❗ Неверный номер листинга.")
        return
    listing = listings[listing_index]
    price = listing["price"]
    buyer_id = str(message.from_user.id)
    buyer = await get_user(buyer_id)
    if buyer.get("balance", 0) < price:
        await message.answer("😔 Недостаточно средств для покупки.")
        return
    new_buyer_balance = buyer.get("balance", 0) - price
    await update_user(buyer_id, balance=new_buyer_balance)
    seller = await get_user(listing["seller_id"])
    if seller:
        new_seller_balance = seller.get("balance", 0) + price
        await update_user(listing["seller_id"], balance=new_seller_balance)
    timestamp = datetime.datetime.now().isoformat()
    await add_token(buyer_id, listing["token"], listing["score"], timestamp, listing["bg_color"], listing["text_color"])
    await remove_market_listing(listing["id"])
    await message.answer(f"🎉 Вы купили номер {listing['token']} за {price} 💎!\nНовый баланс: {new_buyer_balance} 💎.")
    if seller:
        try:
            await bot.send_message(int(listing["seller_id"]),
                                   f"Уведомление: Ваш номер {listing['token']} куплен за {price} 💎.")
        except Exception as e:
            print("Ошибка уведомления продавца:", e)

@dp.message(Command("participants"))
async def list_participants(message: Message) -> None:
    async with db_pool.acquire() as connection:
        rows = await connection.fetch("SELECT * FROM users")
        users = [dict(row) for row in rows]
    if not users:
        await message.answer("❗ Нет зарегистрированных участников.")
        return
    msg = "👥 Участники:\n"
    for user in users:
        tokens = await get_tokens(user["id"])
        cnt = len(tokens)
        msg += f"{user.get('username', 'Неизвестный')} (ID: {user['id']}) — Баланс: {user.get('balance', 0)} 💎, номеров: {cnt}\n"
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
    initiator = await get_user(str(message.from_user.id))
    if target_uid == str(message.from_user.id):
        await message.answer("❗ Нельзя обмениваться с самим собой!")
        return
    target = await get_user(target_uid)
    if not target:
        await message.answer("❗ Пользователь не найден.")
        return
    my_tokens = await get_tokens(str(message.from_user.id))
    target_tokens = await get_tokens(target_uid)
    if my_index < 0 or my_index >= len(my_tokens):
        await message.answer("❗ Неверный номер вашего номера.")
        return
    if target_index < 0 or target_index >= len(target_tokens):
        await message.answer("❗ Неверный номер у пользователя.")
        return
    my_item = my_tokens[my_index]
    target_item = target_tokens[target_index]
    await update_token_owner(my_item["id"], target_uid)
    await update_token_owner(target_item["id"], str(message.from_user.id))
    await message.answer(f"🎉 Обмен завершён!\nВы отдали номер {my_item['token']} и получили {target_item['token']}.")
    try:
        await bot.send_message(int(target_uid),
                               f"🔄 Пользователь {initiator.get('username', 'Неизвестный')} обменял с вами номера.\n"
                               f"Вы отдали {target_item['token']} и получили {my_item['token']}.")
    except Exception as e:
        print("Ошибка уведомления партнёра:", e)

# ====================== Веб-приложение (FastAPI) ======================
app = FastAPI()

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")
templates.env.globals["enumerate"] = enumerate
templates.env.globals["get_rarity"] = get_rarity

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user_id = request.cookies.get("user_id")
    user = await get_user(user_id) if user_id else None
    market = await get_market_listings()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "user_id": user_id,
        "market": market,
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
    user = await get_or_create_user(user_id)
    if user.get("logged_in"):
        response = RedirectResponse(url=f"/profile/{user_id}", status_code=303)
        response.set_cookie("user_id", user_id, max_age=60*60*24*30, path="/")
        return response
    code = generate_login_code()
    expiry = (datetime.datetime.now() + datetime.timedelta(minutes=5)).timestamp()
    await update_user(user_id, login_code=code, code_expiry=expiry)
    try:
        await bot.send_message(int(user_id), f"Ваш код для входа: {code}")
    except Exception as e:
        return HTMLResponse("Ошибка при отправке кода через Telegram.", status_code=500)
    return templates.TemplateResponse("verify.html", {"request": request, "user_id": user_id})

@app.post("/verify", response_class=HTMLResponse)
async def verify_post(request: Request, user_id: str = Form(...), code: str = Form(...)):
    user = await get_user(user_id)
    if not user:
        return HTMLResponse("Пользователь не найден.", status_code=404)
    if user.get("code_expiry", 0) < datetime.datetime.now().timestamp():
        return HTMLResponse("Код устарел. Повторите попытку входа.", status_code=400)
    if user.get("login_code") != code:
        return HTMLResponse("Неверный код.", status_code=400)
    await update_user(user_id, logged_in=1, login_code=None, code_expiry=None)
    response = RedirectResponse(url=f"/profile/{user_id}", status_code=303)
    response.set_cookie("user_id", user_id, max_age=60*60*24*30, path="/")
    return response

@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    user_id = request.cookies.get("user_id")
    if user_id:
        await update_user(user_id, logged_in=0)
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_id", path="/")
    return response

@app.get("/auto_login", response_class=HTMLResponse)
async def auto_login(request: Request, user_id: str):
    user = await get_user(user_id)
    if not user or not user.get("logged_in"):
        return RedirectResponse(url="/login", status_code=303)
    response = RedirectResponse(url=f"/profile/{user_id}", status_code=303)
    response.set_cookie("user_id", user_id, max_age=60*60*24*30, path="/")
    return response

@app.get("/profile/{user_id}", response_class=HTMLResponse)
async def profile(request: Request, user_id: str):
    user = await get_user(user_id)
    if not user:
        return HTMLResponse("Пользователь не найден.", status_code=404)
    current_user_id = request.cookies.get("user_id")
    is_owner = (current_user_id == user_id)
    tokens = await get_tokens(user_id)
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user,
        "user_id": user_id,
        "is_owner": is_owner,
        "tokens": tokens,
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
    user = await get_or_create_user(user_id)
    today = datetime.date.today().isoformat()
    if user.get("last_activation_date") != today:
        await update_user(user_id, last_activation_date=today, activation_count=0)
    if user.get("activation_count", 0) >= 3:
        return templates.TemplateResponse("mint.html", {"request": request, "error": "Вы исчерпали бесплатные активации на сегодня. Попробуйте завтра!", "user_id": user_id})
    new_count = user.get("activation_count", 0) + 1
    await update_user(user_id, activation_count=new_count)
    num, score, bg_color, text_color = generate_number()
    timestamp = datetime.datetime.now().isoformat()
    await add_token(user_id, num, score, timestamp, bg_color, text_color)
    return templates.TemplateResponse("profile.html", {"request": request, "user": await get_user(user_id), "user_id": user_id, "tokens": await get_tokens(user_id)})

@app.get("/sell", response_class=HTMLResponse)
async def web_sell(request: Request):
    return templates.TemplateResponse("sell.html", {"request": request})

@app.post("/sell", response_class=HTMLResponse)
async def web_sell_post(request: Request, user_id: str = Form(None), token_index: int = Form(...), price: int = Form(...)):
    if not user_id:
        user_id = request.cookies.get("user_id")
    if not user_id:
        return HTMLResponse("Ошибка: не найден Telegram ID. Пожалуйста, войдите.", status_code=400)
    tokens = await get_tokens(user_id)
    if token_index < 1 or token_index > len(tokens):
        return HTMLResponse("Неверный номер из вашей коллекции.", status_code=400)
    token_entry = tokens[token_index - 1]
    await remove_token(token_entry["id"])
    listing_time = datetime.datetime.now().isoformat()
    await add_market_listing(user_id, token_entry["token"], token_entry["score"],
                             listing_time, token_entry["bg_color"], token_entry["text_color"], price)
    return templates.TemplateResponse("profile.html", {"request": request, "user": await get_user(user_id), "user_id": user_id, "tokens": await get_tokens(user_id)})

@app.get("/exchange", response_class=HTMLResponse)
async def web_exchange(request: Request):
    return templates.TemplateResponse("exchange.html", {"request": request})

@app.post("/exchange", response_class=HTMLResponse)
async def web_exchange_post(request: Request, user_id: str = Form(None), my_index: int = Form(...), target_id: str = Form(...), target_index: int = Form(...)):
    if not user_id:
        user_id = request.cookies.get("user_id")
    if not user_id:
        return HTMLResponse("Ошибка: не найден Telegram ID. Пожалуйста, войдите.", status_code=400)
    my_token = await get_token_by_index(user_id, my_index - 1)
    target_token = await get_token_by_index(target_id, target_index - 1)
    if not my_token or not target_token:
        return HTMLResponse("Неверный номер у одного из пользователей.", status_code=400)
    await update_token_owner(my_token["id"], target_id)
    await update_token_owner(target_token["id"], user_id)
    return templates.TemplateResponse("profile.html", {"request": request, "user": await get_user(user_id), "user_id": user_id, "tokens": await get_tokens(user_id)})

@app.get("/participants", response_class=HTMLResponse)
async def web_participants(request: Request):
    async with db_pool.acquire() as connection:
        rows = await connection.fetch("SELECT * FROM users")
        users = [dict(row) for row in rows]
    return templates.TemplateResponse("participants.html", {"request": request, "users": users})

@app.get("/market", response_class=HTMLResponse)
async def web_market(request: Request):
    market = await get_market_listings()
    return templates.TemplateResponse("market.html", {"request": request, "market": market, "buyer_id": request.cookies.get("user_id")})

@app.post("/buy/{listing_index}")
async def web_buy(request: Request, listing_index: int, buyer_id: str = Form(None)):
    if not buyer_id:
        buyer_id = request.cookies.get("user_id")
    if not buyer_id:
        return HTMLResponse("Ошибка: не найден Telegram ID. Пожалуйста, войдите.", status_code=400)
    listings = await get_market_listings()
    if listing_index < 0 or listing_index >= len(listings):
        return HTMLResponse("Неверный номер листинга.", status_code=400)
    listing = listings[listing_index]
    seller_id = listing.get("seller_id")
    price = listing["price"]
    buyer = await get_user(buyer_id)
    if not buyer:
        return HTMLResponse("Покупатель не найден.", status_code=404)
    if buyer.get("balance", 0) < price:
        return HTMLResponse("Недостаточно средств.", status_code=400)
    new_buyer_balance = buyer.get("balance", 0) - price
    await update_user(buyer_id, balance=new_buyer_balance)
    seller = await get_user(seller_id)
    if seller:
        new_seller_balance = seller.get("balance", 0) + price
        await update_user(seller_id, balance=new_seller_balance)
    timestamp = datetime.datetime.now().isoformat()
    await add_token(buyer_id, listing["token"], listing["score"], timestamp, listing["bg_color"], listing["text_color"])
    await remove_market_listing(listing["id"])
    return templates.TemplateResponse("profile.html", {"request": request, "user": await get_user(buyer_id), "user_id": buyer_id})

# ====================== Запуск бота и веб-сервера ======================
async def main():
    await init_db()  # Инициализация базы данных PostgreSQL
    bot_task = asyncio.create_task(dp.start_polling(bot))
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    web_task = asyncio.create_task(server.serve())
    await asyncio.gather(bot_task, web_task)

if __name__ == "__main__":
    asyncio.run(main())
