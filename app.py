import os
import sqlite3
import time
import threading
import logging
from datetime import datetime
from flask import Flask
import telebot
from telebot import types

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get("TOKEN")
MAIN_ADMIN = 7905866942  # Ваш Telegram ID
SUPPORT = "@KONS_TZ"
ID_HINT_PHOTO = "https://i.ibb.co/6wXgV0b/1xbet-id-hint.jpg"

if not TOKEN:
    raise ValueError("ОШИБКА: Переменная окружения TOKEN не задана!")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

bot_active = True
temp_data = {}

# ========== БАЗА ДАННЫХ ==========
def get_db_connection():
    return sqlite3.connect('database.db', timeout=20)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, join_date TEXT, saved_1xbet_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins (chat_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, account_id TEXT, photo_id TEXT, status TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdraws (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, bookmaker TEXT, elqr_photo_id TEXT, account_id TEXT, secure_code TEXT, status TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS qr_codes (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, date TEXT)''')
    c.execute('INSERT OR IGNORE INTO admins (chat_id) VALUES (?)', (MAIN_ADMIN,))
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN saved_1xbet_id TEXT')
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    conn.close()

def add_user(chat_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (chat_id, join_date) VALUES (?, ?)', (chat_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT chat_id FROM users')
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def save_user_id(chat_id, account_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET saved_1xbet_id = ? WHERE chat_id = ?', (str(account_id).strip(), chat_id))
    conn.commit()
    conn.close()

def get_saved_user_id(chat_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT saved_1xbet_id FROM users WHERE chat_id = ?', (chat_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_admins():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT chat_id FROM admins')
    admins = [row[0] for row in c.fetchall()]
    conn.close()
    if MAIN_ADMIN not in admins:
        add_admin(MAIN_ADMIN)
        admins.append(MAIN_ADMIN)
    return admins

def add_admin(chat_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO admins (chat_id) VALUES (?)', (chat_id,))
    conn.commit()
    conn.close()

def remove_admin(chat_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM admins WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

def add_deposit(user_id, amount, account_id, photo_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO deposits (user_id, amount, account_id, photo_id, status, date) VALUES (?, ?, ?, ?, ?, ?)',
              (user_id, amount, account_id, photo_id, 'pending', datetime.now().strftime("%d.%m.%Y %H:%M")))
    dep_id = c.lastrowid
    conn.commit()
    conn.close()
    return dep_id

def update_deposit_status(dep_id, status):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE deposits SET status = ? WHERE id = ?', (status, dep_id))
    conn.commit()
    conn.close()

def get_pending_deposits():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, user_id, amount, account_id, photo_id, date FROM deposits WHERE status = "pending"')
    rows = c.fetchall()
    conn.close()
    return rows

def add_withdraw(user_id, bookmaker, elqr_photo_id, account_id, secure_code):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO withdraws (user_id, bookmaker, elqr_photo_id, account_id, secure_code, status, date) VALUES (?, ?, ?, ?, ?, ?, ?)',
              (user_id, bookmaker, elqr_photo_id, account_id, secure_code, 'pending', datetime.now().strftime("%d.%m.%Y %H:%M")))
    w_id = c.lastrowid
    conn.commit()
    conn.close()
    return w_id

def update_withdraw_status(w_id, status):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE withdraws SET status = ? WHERE id = ?', (status, w_id))
    conn.commit()
    conn.close()

def get_pending_withdraws():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, user_id, bookmaker, elqr_photo_id, account_id, secure_code, date FROM withdraws WHERE status = "pending"')
    rows = c.fetchall()
    conn.close()
    return rows

def save_qr(file_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO qr_codes (file_id, date) VALUES (?, ?)', (file_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
    conn.commit()
    conn.close()

def get_last_qr():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT file_id FROM qr_codes ORDER BY id DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

init_db()# ========== МЕНЮ БОТА ==========
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 Пополнение", "💸 Вывод")
    markup.add("👨‍💻 Поддержка")
    if user_id in get_admins():
        markup.add("⚙️ Admin панель")
    return markup

def admin_menu():
    global bot_active
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📋 Заявки Пополнение", "📤 Заявки Вывод")
    markup.add("📊 Статистика", "🖼 Изменить QR")
    markup.add("➕ Добавить админа", "➖ Удалить админа")  # Добавлена кнопка удаления
    markup.add("📢 Рассылка", "🔙 Главное меню")          # Добавлена кнопка рассылки
    status_btn = "🔴 ВЫКЛЮЧИТЬ БОТА" if bot_active else "🟢 ВКЛЮЧИТЬ БОТА"
    markup.add(status_btn)
    return markup

def back_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔙 Назад")
    return markup

def id_input_menu(user_id):
    saved_id = get_saved_user_id(user_id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    if saved_id:
        markup.add(types.KeyboardButton(text=saved_id))
    markup.add(types.KeyboardButton(text="Отмена"))
    return markup

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_user_mention(user_id):
    try:
        chat = bot.get_chat(user_id)
        if chat.username:
            return f"@{chat.username}"
        else:
            return f"{chat.first_name or 'Без имени'}"
    except Exception:
        return f"ID: {user_id}"

def delete_msg_after_delay(chat_id, message_id, delay=300):
    time.sleep(delay)
    try:
        bot.delete_message(chat_id, message_id)
        logging.info(f"Сообщение {message_id} удалено по таймеру.")
    except Exception as e:
        logging.error(f"Не удалось удалить сообщение {message_id}: {e}")

# ========== ФИЛЬТРЫ И СТАРТ ==========
@bot.message_handler(func=lambda m: not bot_active and m.from_user.id not in get_admins())
def bot_disabled(msg):
    bot.send_message(msg.chat.id, "🔴 Бот временно недоступен. Зайдите позже.")

@bot.message_handler(content_types=['photo'], func=lambda m: m.chat.id in get_admins())
def catch_photo_file_id(msg):
    bot.reply_to(msg, f"ℹ️ File ID этого изображения:\n\n`{msg.photo[-1].file_id}`", parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def start(msg):
    temp_data.pop(msg.chat.id, None)
    add_user(msg.chat.id)
    bot.send_message(msg.chat.id, 
        f"✨ Добро пожаловать, {msg.from_user.first_name}!\n\n🏦 BMkassa - ваш надежный финансовый помощник\n\n👇 Выберите действие:", 
        reply_markup=main_menu(msg.from_user.id))

@bot.message_handler(func=lambda m: m.text in ["🔙 Назад", "Отмена", "🔙 Главное меню"])
def back_to_main(msg):
    temp_data.pop(msg.chat.id, None)
    start(msg)

@bot.message_handler(func=lambda m: m.text == "👨‍💻 Поддержка")
def support_info(msg):
    bot.send_message(msg.chat.id, f"📞 Поддержка: {SUPPORT}\n\nОтветим в течение 15 минут!")# ========== ЛОГИКА ПОПОЛНЕНИЯ ==========
@bot.message_handler(func=lambda m: m.text == "💰 Пополнение")
def deposit(msg):
    markup = id_input_menu(msg.chat.id)
    try:
        bot.send_photo(msg.chat.id, ID_HINT_PHOTO, caption="🆔 Введите ID счета для пополнения:", reply_markup=markup)
    except Exception:
        bot.send_message(msg.chat.id, "🆔 Введите ID счета для пополнения:", reply_markup=markup)
    bot.register_next_step_handler(msg, get_account_id)

def get_account_id(msg):
    if msg.text in ["🔙 Назад", "Отмена"]:
        temp_data.pop(msg.chat.id, None)
        start(msg)
        return
    
    account_id = msg.text
    temp_data[msg.chat.id] = {"account_id": account_id}
    bot.send_message(msg.chat.id, "💰 Введите сумму (от 100 до 100 000 сом):", reply_markup=back_menu())
    bot.register_next_step_handler(msg, get_amount)

def get_amount(msg):
    if msg.text == "🔙 Назад":
        temp_data.pop(msg.chat.id, None)
        start(msg)
        return
        
    if not msg.text.isdigit():
        bot.send_message(msg.chat.id, "❌ Введите число цифрами!", reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_amount)
        return
        
    amount = int(msg.text)
    if amount < 100 or amount > 100000:
        bot.send_message(msg.chat.id, "❌ Сумма должна быть от 100 до 100 000 сом!", reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_amount)
        return
    
    user_id = msg.chat.id
    if user_id not in temp_data:
        bot.send_message(msg.chat.id, "❌ Сессия истекла. Начните заново.")
        start(msg)
        return
        
    temp_data[user_id]["amount"] = amount
    account_id = temp_data[user_id]["account_id"]
    
    instruction_text = (
        f"Прикрепите скриншот чека «📎»\n\n"
        f"Аккаунт ID: {account_id}\n"
        f"Сумма: {amount} KGS✅\n\n"
        f"❗️Оплатите и отправьте скриншот чека в течении 5 минут, "
        f"чек должен быть в формате картинки⚠️"
    )
    
    qr_file_id = get_last_qr()
    
    if qr_file_id:
        sent_msg = bot.send_photo(msg.chat.id, qr_file_id, caption=instruction_text)
    else:
        sent_msg = bot.send_message(msg.chat.id, f"📱 QR-код временно отсутствует. Свяжитесь с поддержкой: {SUPPORT}\n\n{instruction_text}")
    
    threading.Thread(
        target=delete_msg_after_delay, 
        args=(msg.chat.id, sent_msg.message_id, 300), 
        daemon=True
    ).start()
    
    bot.register_next_step_handler(msg, get_check_photo)

def get_check_photo(msg):
    if msg.text == "🔙 Назад":
        temp_data.pop(msg.chat.id, None)
        start(msg)
        return
        
    if not msg.photo:
        bot.send_message(msg.chat.id, "❌ Отправьте именно ФОТОГРАФИЮ чека!", reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_check_photo)
        return
    
    user_id = msg.chat.id
    user_session = temp_data.get(user_id)
    
    if not user_session:
        bot.send_message(msg.chat.id, "❌ Ошибка сессии! Начните пополнение заново.")
        start(msg)
        return
        
    account_id = user_session["account_id"]
    amount = user_session["amount"]
    photo_id = msg.photo[-1].file_id
    
    dep_id = add_deposit(user_id, amount, account_id, photo_id)
    save_user_id(user_id, account_id)
    temp_data.pop(user_id, None)
    
    admins = get_admins()
    username_mention = get_user_mention(user_id)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}")
    )
    
    for admin in admins:
        try:
            bot.send_photo(admin, photo_id, 
                caption=f"🆕 НОВАЯ ЗАЯВКА НА ПОПОЛНЕНИЕ #{dep_id}\n"
                        f"👤 Юзернейм: {username_mention}\n"
                        f"🆔 Счет БК: {account_id}\n"
                        f"💰 Сумма: {amount} сом\n"
                        f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                reply_markup=markup)
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление админу {admin}: {e}")
    
    bot.send_message(msg.chat.id, "✅ Заявка на пополнение отправлена!\n⏳ Ожидайте подтверждения администратора.", reply_markup=main_menu(user_id))


# ========== ЛОГИКА ВЫВОДА СРЕДСТВ ==========
@bot.message_handler(func=lambda m: m.text == "💸 Вывод")
def withdraw_start(msg):
    temp_data[msg.chat.id] = {"bookmaker": "1XBET"}
    bot.send_message(msg.chat.id, "Прикрепите ваш ELQR", reply_markup=back_menu())
    bot.register_next_step_handler(msg, get_withdraw_elqr)

def get_withdraw_elqr(msg):
    if msg.text == "🔙 Назад":
        temp_data.pop(msg.chat.id, None)
        start(msg)
        return
    if not msg.photo:
        bot.send_message(msg.chat.id, "❌ Пожалуйста, отправьте фото вашего ELQR кода!", reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_withdraw_elqr)
        return
        
    temp_data[msg.chat.id]["elqr_photo_id"] = msg.photo[-1].file_id
    
    markup = id_input_menu(msg.chat.id)
    try:
        bot.send_photo(msg.chat.id, ID_HINT_PHOTO, caption="Отправьте ваш ID 1xbet", reply_markup=markup)
    except Exception:
        bot.send_message(msg.chat.id, "Отправьте ваш ID 1xbet", reply_markup=markup)
        
    bot.register_next_step_handler(msg, get_withdraw_id)

def get_withdraw_id(msg):
    if msg.text in ["🔙 Назад", "Отмена"]:
        temp_data.pop(msg.chat.id, None)
        start(msg)
        return
    
    account_id = msg.text
    temp_data[msg.chat.id]["account_id"] = account_id
    
    instruction = (
        "📌 Как вывести средства с 1ХБЕТ\n\n"
        "1️⃣ Зайдите в раздел “Настройки”\n"
        "2️⃣ Выберите способ вывода — “Наличные”\n"
        "3️⃣ При заполнении данных укажите:\n\n"
        "📍 Город: Бишкек\n"
        "🚩 Улица: BMkassa\n\n"
        "✉️ После оформления заявки пришлите полученный код боту"
    )
    
    bot.send_message(msg.chat.id, instruction, reply_markup=back_menu())
    bot.register_next_step_handler(msg, get_withdraw_code)

def get_withdraw_code(msg):
    if msg.text == "🔙 Назад":
        temp_data.pop(msg.chat.id, None)
        start(msg)
        return
        
    user_id = msg.chat.id
    session = temp_data.get(user_id)
    
    if not session:
        bot.send_message(user_id, "❌ Сессия истекла, начните заново.")
        start(msg)
        return
        
    secure_code = msg.text
    bookmaker = session["bookmaker"]
    elqr_photo_id = session["elqr_photo_id"]
    account_id = session["account_id"]
    
    w_id = add_withdraw(user_id, bookmaker, elqr_photo_id, account_id, secure_code)
    save_user_id(user_id, account_id)
    temp_data.pop(user_id, None)
    
    admins = get_admins()
    username_mention = get_user_mention(user_id)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Выплачено", callback_data=f"wapprove_{w_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"wreject_{w_id}")
    )
    
    for admin in admins:
        try:
            bot.send_photo(admin, elqr_photo_id, 
                caption=f"📤 ЗАЯВКА НА ВЫВОД #{w_id}\n"
                        f"👤 Юзернейм: {username_mention}\n"
                        f"🆔 ID в БК: {account_id}\n"
                        f"🎰 Букмекер: {bookmaker}\n"
                        f"🔑 Код подтверждения: {secure_code}\n"
                        f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                reply_markup=markup)
        except Exception as e:
            logging.error(f"Не удалось отправить вывод админу {admin}: {e}")
            
    bot.send_message(user_id, "✅ Готово! Средства будут обработаны после подтверждения кода.", reply_markup=main_menu(user_id))# ========== АДМИН ПАНЕЛЬ ==========
@bot.message_handler(func=lambda m: m.text == "⚙️ Admin панель" and m.from_user.id in get_admins())
def admin_panel(msg):
    bot.send_message(msg.chat.id, "⚙️ Добро пожаловать в панель управления", reply_markup=admin_menu())

# --- Управление админами: ДОБАВЛЕНИЕ ---
@bot.message_handler(func=lambda m: m.text == "➕ Добавить админа" and m.from_user.id in get_admins())
def add_admin_btn(msg):
    bot.send_message(msg.chat.id, "👤 Отправьте Telegram ID пользователя цифрами:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, process_add_admin)

def process_add_admin(msg):
    if msg.text == "🔙 Назад":
        admin_panel(msg)
        return
    try:
        new_admin_id = int(msg.text)
        add_admin(new_admin_id)
        bot.send_message(msg.chat.id, f"✅ ID {new_admin_id} добавлен в админы!", reply_markup=admin_menu())
    except ValueError:
        bot.send_message(msg.chat.id, "❌ Ошибка! ID должен состоять только из цифр.", reply_markup=admin_menu())

# --- Управление админами: УДАЛЕНИЕ ---
@bot.message_handler(func=lambda m: m.text == "➖ Удалить админа" and m.from_user.id in get_admins())
def remove_admin_btn(msg):
    bot.send_message(msg.chat.id, "👤 Отправьте Telegram ID админа, которого нужно УДАЛИТЬ:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, process_remove_admin)

def process_remove_admin(msg):
    if msg.text == "🔙 Назад":
        admin_panel(msg)
        return
    try:
        target_id = int(msg.text)
        if target_id == MAIN_ADMIN:
            bot.send_message(msg.chat.id, "❌ Нельзя удалить создателя бота (Главного админа)!", reply_markup=admin_menu())
            return
            
        if target_id not in get_admins():
            bot.send_message(msg.chat.id, "❌ Этот ID не найден в списке администраторов.", reply_markup=admin_menu())
            return
            
        remove_admin(target_id)
        bot.send_message(msg.chat.id, f"✅ Администратор с ID {target_id} успешно удален.", reply_markup=admin_menu())
    except ValueError:
        bot.send_message(msg.chat.id, "❌ Ошибка! ID должен состоять только из цифр.", reply_markup=admin_menu())

# --- ФУНКЦИЯ РАССЫЛКИ ---
@bot.message_handler(func=lambda m: m.text == "📢 Рассылка" and m.from_user.id in get_admins())
def start_broadcast(msg):
    bot.send_message(msg.chat.id, "📢 Отправьте сообщение для рассылки всем пользователям.\nЭто может быть как текст, так и картинка с описанием.", reply_markup=back_menu())
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(msg):
    if msg.text == "🔙 Назад":
        admin_panel(msg)
        return
        
    users = get_all_users()
    if not users:
        bot.send_message(msg.chat.id, "❌ В базе данных нет пользователей для рассылки.", reply_markup=admin_menu())
        return
        
    bot.send_message(msg.chat.id, f"⏳ Начинаю рассылку для {len(users)} пользователей...", reply_markup=admin_menu())
    
    success_count = 0
    fail_count = 0
    
    for user_id in users:
        try:
            # Если админ отправил картинку с текстом
            if msg.photo:
                bot.send_photo(user_id, msg.photo[-1].file_id, caption=msg.caption)
            # Если админ отправил просто текст
            elif msg.text:
                bot.send_message(user_id, msg.text)
            success_count += 1
            time.sleep(0.05)  # Защита от лимитов Telegram
        except Exception:
            fail_count += 1
            
    bot.send_message(msg.chat.id, f"📊 Результаты рассылки:\n\n✅ Успешно доставлено: {success_count}\n❌ Ошибок (Бот заблокирован): {fail_count}")

# --- Другие админские функции ---
@bot.message_handler(func=lambda m: m.text in ["🔴 ВЫКЛЮЧИТЬ БОТА", "🟢 ВКЛЮЧИТЬ БОТА"] and m.from_user.id in get_admins())
def toggle_bot(msg):
    global bot_active
    if msg.text == "🔴 ВЫКЛЮЧИТЬ БОТА":
        bot_active = False
        bot.send_message(msg.chat.id, "🔴 Бот ВЫКЛЮЧЕН для обычных пользователей.", reply_markup=admin_menu())
    else:
        bot_active = True
        bot.send_message(msg.chat.id, "🟢 Бот ВКЛЮЧЕН. Все функции доступны.", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📋 Заявки Пополнение" and m.from_user.id in get_admins())
def view_requests(msg):
    deposits = get_pending_deposits()
    if not deposits:
        bot.send_message(msg.chat.id, "📭 Активные заявки на пополнение отсутствуют.", reply_markup=admin_menu())
        return
    for dep in deposits:
        dep_id, user_id, amount, account_id, photo_id, date = dep
        username_mention = get_user_mention(user_id)
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}")
        )
        caption_text = f"🆕 ЗАЯВКА НА ПОПОЛНЕНИЕ #{dep_id}\n👤 Юзернейм: {username_mention}\n🆔 Счет: {account_id}\n💰 {amount} сом\n📅 {date}"
        try: bot.send_photo(msg.chat.id, photo_id, caption=caption_text, reply_markup=markup)
        except Exception: bot.send_message(msg.chat.id, caption_text, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📤 Заявки Вывод" and m.from_user.id in get_admins())
def view_withdraw_requests(msg):
    withdraws = get_pending_withdraws()
    if not withdraws:
        bot.send_message(msg.chat.id, "📭 Активные заявки на вывод отсутствуют.", reply_markup=admin_menu())
        return
    for w in withdraws:
        w_id, user_id, bookmaker, elqr_photo_id, account_id, secure_code, date = w
        username_mention = get_user_mention(user_id)
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Выплачено", callback_data=f"wapprove_{w_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"wreject_{w_id}")
        )
        caption_text = f"📤 ЗАЯВКА НА ВЫВОД #{w_id}\n👤 Юзернейм: {username_mention}\n🆔 ID в БК: {account_id}\n🎰 БК: {bookmaker}\n🔑 Код: {secure_code}\n📅 {date}"
        try: bot.send_photo(msg.chat.id, elqr_photo_id, caption=caption_text, reply_markup=markup)
        except Exception: bot.send_message(msg.chat.id, caption_text, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📊 Статистика" and m.from_user.id in get_admins())
def stats(msg):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    users = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM deposits WHERE status="approved"')
    approved_dep = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM withdraws WHERE status="approved"')
    approved_wit = c.fetchone()[0]
    conn.close()
    
    bot.send_message(msg.chat.id, 
        f"📊 СТАТИСТИКА СИСТЕМЫ\n\n"
        f"👥 Всего пользователей: {users}\n"
        f"✅ Успешных пополнений: {approved_dep}\n"
        f"📤 Успешных выводов: {approved_wit}\n"
        f"🟢 Статус системы: {'АКТИВЕН' if bot_active else 'ВЫКЛЮЧЕН'}", 
        reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "🖼 Изменить QR" and m.from_user.id in get_admins())
def change_qr(msg):
    bot.send_message(msg.chat.id, "🖼 Отправьте новый QR-код в виде изображения:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, save_new_qr)

def save_new_qr(msg):
    if msg.text == "🔙 Назад":
        admin_panel(msg)
        return
    if msg.photo:
        file_id = msg.photo[-1].file_id
        save_qr(file_id)
        bot.send_message(msg.chat.id, "✅ Новый QR-код успешно сохранен!", reply_markup=admin_menu())
    else:
        bot.send_message(msg.chat.id, "❌ Ошибка! Нужно отправить картинку.", reply_markup=back_menu())
        bot.register_next_step_handler(msg, save_new_qr)# ========== ОБРАБОТКА ИНЛАЙН КНОПОК ==========
@bot.callback_query_handler(func=lambda call: True)
def handle_call(call):
    admin_id = call.from_user.id
    if admin_id not in get_admins():
        bot.answer_callback_query(call.id, "❌ У вас нет прав админа!")
        return
    
    data_parts = call.data.split('_')
    action = data_parts[0]
    target_id = int(data_parts[1])
    
    conn = get_db_connection()
    c = conn.cursor()
    
    if action in ["approve", "reject"]:
        c.execute('SELECT user_id, amount, status FROM deposits WHERE id = ?', (target_id,))
        res = c.fetchone()
        if not res or res[2] != "pending":
            bot.answer_callback_query(call.id, "⚠️ Заявка уже обработана!")
            conn.close()
            return
        user_id, amount, _ = res
        
        if action == "approve":
            update_deposit_status(target_id, "approved")
            bot.answer_callback_query(call.id, "✅ Одобрено")
            try: bot.send_message(user_id, f"✅ Ваша заявка на пополнение {amount} сом ОДОБРЕНА!")
            except Exception: pass
            status_text = "✅ ОДОБРЕНО"
        else:
            update_deposit_status(target_id, "rejected")
            bot.answer_callback_query(call.id, "❌ Отклонено")
            try: bot.send_message(user_id, f"❌ Ваша заявка на пополнение {amount} сом ОТКЛОНЕНА! Обратитесь в поддержку: {SUPPORT}")
            except Exception: pass
            status_text = "❌ ОТКЛОНЕНО"
            
        try: bot.edit_message_caption(f"{status_text} ДЛЯ ЗАЯВКИ ПОПОЛНЕНИЯ #{target_id}", call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception: pass

    elif action in ["wapprove", "wreject"]:
        c.execute('SELECT user_id, bookmaker, status FROM withdraws WHERE id = ?', (target_id,))
        res = c.fetchone()
        if not res or res[2] != "pending":
            bot.answer_callback_query(call.id, "⚠️ Заявка уже обработана!")
            conn.close()
            return
        user_id, bookmaker, _ = res
        
        if action == "wapprove":
            update_withdraw_status(target_id, "approved")
            bot.answer_callback_query(call.id, "✅ Средства выплачены")
            try: bot.send_message(user_id, f"✅ Ваш запрос на вывод с {bookmaker} успешно обработан! Средства отправлены на ваш ELQR.")
            except Exception: pass
            status_text = "✅ ВЫПЛАЧЕНО"
        else:
            update_withdraw_status(target_id, "rejected")
            bot.answer_callback_query(call.id, "❌ Вывод отклонен")
            try: bot.send_message(user_id, f"❌ Ваш запрос на вывод с {bookmaker} отклонен администрацией. Проверьте правильность кода или напишите в поддержку: {SUPPORT}")
            except Exception: pass
            status_text = "❌ ОТКЛОНЕНО"
            
        try: bot.edit_message_caption(f"{status_text} ДЛЯ ЗАЯВКИ НА ВЫВОД #{target_id}", call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception: pass

    conn.close()

# ========== FLASK CONFIG ==========
@app.route('/health')
def health():
    return "OK", 200

@app.route('/')
def home():
    return "BMkassa Bot is running!"

def run_bot():
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=40)
        except Exception as e:
            logging.error(f"Ошибка пуллинга: {e}")
            time.sleep(10)

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
