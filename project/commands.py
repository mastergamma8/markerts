# commands.py
import datetime
from aiogram import types
from aiogram.filters import Command
from aiogram.types import Message
from utils import load_data, save_data, ensure_user, generate_number, generate_login_code
from bot import dp, bot

@dp.message(Command("start"))
async def start_cmd(message: Message) -> None:
    data = load_data()
    ensure_user(data, str(message.from_user.id), message.from_user.username or message.from_user.first_name)
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
async def login_cmd(message: Message) -> None:
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❗ Формат: /login <Ваш Telegram ID>")
        return
    user_id = parts[1]
    if user_id != str(message.from_user.id):
        await message.answer("❗ Вы можете войти только в свой аккаунт.")
        return
    data = load_data()
    user = ensure_user(data, user_id, message.from_user.username or message.from_user.first_name)
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

@dp.message(Command("verify"))
async def verify_cmd(message: Message) -> None:
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
async def logout_cmd(message: Message) -> None:
    user_id = str(message.from_user.id)
    data = load_data()
    user = data.get("users", {}).get(user_id)
    if user:
        user["logged_in"] = False
        save_data(data)
    await message.answer("Вы вышли из аккаунта. Для входа используйте /login <Ваш Telegram ID>.")

@dp.message(Command("setavatar"))
async def setavatar_cmd(message: Message) -> None:
    if message.caption and message.caption.startswith("/setavatar"):
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
        data = load_data()
        user = ensure_user(data, str(message.from_user.id), message.from_user.username or message.from_user.first_name)
        user["photo_url"] = file_url
        save_data(data)
        await message.answer("✅ Аватар обновлён!")

@dp.message(Command("mint"))
async def mint_cmd(message: Message) -> None:
    data = load_data()
    user = ensure_user(data, str(message.from_user.id), message.from_user.username or message.from_user.first_name)
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
async def collection_cmd(message: Message) -> None:
    data = load_data()
    user = ensure_user(data, str(message.from_user.id))
    tokens = user.get("tokens", [])
    if not tokens:
        await message.answer("😕 У вас пока нет номеров. Используйте /mint для создания.")
        return
    msg = "🎨 " + "\n".join(f"{idx}. {t['token']} | Оценка: {t['score']}" for idx, t in enumerate(tokens, start=1))
    await message.answer(msg)

@dp.message(Command("balance"))
async def balance_cmd(message: Message) -> None:
    data = load_data()
    user = ensure_user(data, str(message.from_user.id))
    await message.answer(f"💎 Ваш баланс: {user.get('balance', 0)} 💎")

@dp.message(Command("sell"))
async def sell_cmd(message: Message) -> None:
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
async def market_cmd(message: Message) -> None:
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
async def buy_cmd(message: Message) -> None:
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
            await bot.send_message(int(seller_id), f"Уведомление: Ваш номер {listing['token']} куплен за {price} 💎.")
        except Exception as e:
            print("Ошибка уведомления продавца:", e)

@dp.message(Command("participants"))
async def participants_cmd(message: Message) -> None:
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
async def exchange_cmd(message: Message) -> None:
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
