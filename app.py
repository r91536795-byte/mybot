import os
import sqlite3
from datetime import datetime
from flask import Flask, request
import telebot
from telebot import types

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get("TOKEN")
MAIN_ADMIN = 8763658506  # ЗАМЕНИ НА СВОЙ ТЕЛЕГРАМ ID
SUPPORT = "@KONS_TZ"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ========== ПЕРЕМЕННАЯ ДЛЯ ВКЛ/ВЫКЛ БОТА ==========
bot_active = True

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, join_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins (chat_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, account_id TEXT, photo_id TEXT, status TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS qr_codes (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, date TEXT)''')
    c.execute('INSERT OR IGNORE INTO admins (chat_id) VALUES (?)', (MAIN_ADMIN,))
    conn.commit()
    conn.close()

def add_user(chat_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (chat_id, join_date) VALUES (?, ?)', (chat_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
    conn.commit()
    conn.close()

def get_admins():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT chat_id FROM admins')
    admins = [row[0] for row in c.fetchall()]
    conn.close()
    return admins

def add_admin(chat_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO admins (chat_id) VALUES (?)', (chat_id,))
    conn.commit()
    conn.close()

def remove_admin(chat_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('DELETE FROM admins WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

def add_deposit(user_id, amount, account_id, photo_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('INSERT INTO deposits (user_id, amount, account_id, photo_id, status, date) VALUES (?, ?, ?, ?, ?, ?)',
              (user_id, amount, account_id, photo_id, 'pending', datetime.now().strftime("%d.%m.%Y %H:%M")))
    dep_id = c.lastrowid
    conn.commit()
    conn.close()
    return dep_id

def update_deposit_status(dep_id, status):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('UPDATE deposits SET status = ? WHERE id = ?', (status, dep_id))
    conn.commit()
    conn.close()

def get_pending_deposits():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT id, user_id, amount, account_id, photo_id, date FROM deposits WHERE status = "pending"')
    rows = c.fetchall()
    conn.close()
    return rows

def save_qr(file_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('INSERT INTO qr_codes (file_id, date) VALUES (?, ?)', (file_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
    conn.commit()
    conn.close()

def get_last_qr():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT file_id FROM qr_codes ORDER BY id DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

init_db()

# ========== МЕНЮ БОТА ==========
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 Пополнение", "💸 Вывод")
    markup.add("👨‍💻 Поддержка")
    if user_id in get_admins():
        markup.add("⚙️ Админ панель")
    return markup

def admin_menu():
    global bot_active
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📋 Заявки", "📊 Статистика")
    markup.add("🖼 Изменить QR", "➕ Добавить админа")
    status_btn = "🔴 ВЫКЛЮЧИТЬ БОТА" if bot_active else "🟢 ВКЛЮЧИТЬ БОТА"
    markup.add(status_btn)
    markup.add("🔙 Главное меню")
    return markup

# ========== КОМАНДЫ БОТА ==========
@bot.message_handler(commands=['start'])
def start(msg):
    add_user(msg.chat.id)
    bot.send_message(msg.chat.id, 
        f"✨ Добро пожаловать, {msg.from_user.first_name}!\n\n🏦 BMkassa - ваш надежный финансовый помощник\n\n👇 Выберите действие:", 
        reply_markup=main_menu(msg.from_user.id))

# ФИЛЬТР: если бот выключен, только админы могут писать
@bot.message_handler(func=lambda m: not bot_active and m.from_user.id not in get_admins())
def bot_disabled(msg):
    bot.send_message(msg.chat.id, "🔴 Бот временно недоступен. Зайдите позже.")

@bot.message_handler(func=lambda m: m.text == "👨‍💻 Поддержка")
def support(msg):
    if not bot_active and msg.from_user.id not in get_admins():
        bot.send_message(msg.chat.id, "🔴 Бот недоступен.")
        return
    bot.send_message(msg.chat.id, f"📞 Поддержка: {SUPPORT}\n\nОтветим в течение 15 минут!")

# ========== ПОПОЛНЕНИЕ (ID + Сумма + QR + Чек) ==========
@bot.message_handler(func=lambda m: m.text == "💰 Пополнение")
def deposit(msg):
    if not bot_active and msg.from_user.id not in get_admins():
        bot.send_message(msg.chat.id, "🔴 Пополнение временно недоступно.")
        return
    
    # Отправляем QR код если есть
    qr_file_id = get_last_qr()
    if qr_file_id:
        bot.send_photo(msg.chat.id, qr_file_id, caption="📱 Отсканируйте QR-код для оплаты")
    else:
        bot.send_message(msg.chat.id, "📱 QR-код для оплаты временно отсутствует")
    
    bot.send_message(msg.chat.id, "🆔 Введите ID счета для пополнения:")
    bot.register_next_step_handler(msg, get_account_id)

def get_account_id(msg):
    if msg.text == "🔙 Назад":
        start(msg)
        return
    account_id = msg.text
    bot.send_message(msg.chat.id, "💰 Введите сумму (от 100 до 100 000 сом):")
    bot.register_next_step_handler(msg, lambda m: get_amount(m, account_id))

def get_amount(msg, account_id):
    if not msg.text.isdigit():
        bot.send_message(msg.chat.id, "❌ Введите число!")
        bot.register_next_step_handler(msg, lambda m: get_amount(m, account_id))
        return
    amount = int(msg.text)
    if amount < 100 or amount > 100000:
        bot.send_message(msg.chat.id, "❌ Сумма от 100 до 100 000 сом!")
        bot.register_next_step_handler(msg, lambda m: get_amount(m, account_id))
        return
    
    # Сохраняем временные данные
    temp_data[msg.chat.id] = {"account_id": account_id, "amount": amount}
    bot.send_message(msg.chat.id, "📸 Отправьте ФОТО ЧЕКА для подтверждения оплаты:")
    bot.register_next_step_handler(msg, get_check_photo)

temp_data = {}

def get_check_photo(msg):
    if not msg.photo:
        bot.send_message(msg.chat.id, "❌ Отправьте фото чека!")
        bot.register_next_step_handler(msg, get_check_photo)
        return
    
    user_id = msg.chat.id
    account_id = temp_data.get(user_id, {}).get("account_id")
    amount = temp_data.get(user_id, {}).get("amount")
    photo_id = msg.photo[-1].file_id
    
    if not account_id or not amount:
        bot.send_message(msg.chat.id, "❌ Ошибка! Начните пополнение заново.")
        return
    
    dep_id = add_deposit(user_id, amount, account_id, photo_id)
    
    # Отправляем админам
    admins = get_admins()
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}")
    )
    
    for admin in admins:
        try:
            bot.send_photo(admin, photo_id, 
                caption=f"🆕 НОВАЯ ЗАЯВКА #{dep_id}\n"
                        f"👤 Пользователь: {user_id}\n"
                        f"💰 Сумма: {amount} сом\n"
                        f"🆔 Счет: {account_id}\n"
                        f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                reply_markup=markup)
        except:
            pass
    
    bot.send_message(msg.chat.id, 
        f"✅ Заявка отправлена!\n\n"
        f"💰 Сумма: {amount} сом\n"
        f"🆔 Счет: {account_id}\n\n"
        f"⏳ Ожидайте подтверждения администратора.")
    
    # Очищаем временные данные
    if user_id in temp_data:
        del temp_data[user_id]

@bot.message_handler(func=lambda m: m.text == "💸 Вывод")
def withdraw(msg):
    if not bot_active and msg.from_user.id not in get_admins():
        bot.send_message(msg.chat.id, "🔴 Вывод временно недоступен.")
        return
    bot.send_message(msg.chat.id, f"💸 Для вывода средств обратитесь в поддержку: {SUPPORT}")

# ========== АДМИН ПАНЕЛЬ ==========
@bot.message_handler(func=lambda m: m.text == "⚙️ Админ панель" and m.from_user.id in get_admins())
def admin_panel(msg):
    bot.send_message(msg.chat.id, "⚙️ Админ панель", reply_markup=admin_menu())

# КНОПКА ДОБАВИТЬ АДМИНА
@bot.message_handler(func=lambda m: m.text == "➕ Добавить админа" and m.from_user.id in get_admins())
def add_admin_btn(msg):
    bot.send_message(msg.chat.id, "👤 Отправьте Telegram ID пользователя, которого хотите сделать админом:")
    bot.register_next_step_handler(msg, process_add_admin)

def process_add_admin(msg):
    try:
        new_admin_id = int(msg.text)
        add_admin(new_admin_id)
        bot.send_message(msg.chat.id, f"✅ Пользователь {new_admin_id} добавлен в админы!", reply_markup=admin_menu())
    except:
        bot.send_message(msg.chat.id, "❌ Ошибка! Отправьте числовой ID.", reply_markup=admin_menu())

# КНОПКА ВКЛЮЧЕНИЯ/ВЫКЛЮЧЕНИЯ БОТА
@bot.message_handler(func=lambda m: m.text in ["🔴 ВЫКЛЮЧИТЬ БОТА", "🟢 ВКЛЮЧИТЬ БОТА"] and m.from_user.id in get_admins())
def toggle_bot(msg):
    global bot_active
    if msg.text == "🔴 ВЫКЛЮЧИТЬ БОТА":
        bot_active = False
        bot.send_message(msg.chat.id, "🔴 Бот ВЫКЛЮЧЕН. Пользователи не смогут им пользоваться.", reply_markup=admin_menu())
    else:
        bot_active = True
        bot.send_message(msg.chat.id, "🟢 Бот ВКЛЮЧЕН. Все функции доступны.", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📋 Заявки" and m.from_user.id in get_admins())
def view_requests(msg):
    deposits = get_pending_deposits()
    if not deposits:
        bot.send_message(msg.chat.id, "📭 Нет новых заявок")
        return
    for dep in deposits:
        dep_id, user_id, amount, account_id, photo_id, date = dep
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}")
        )
        try:
            bot.send_photo(msg.chat.id, photo_id,
                caption=f"🆕 ЗАЯВКА #{dep_id}\n👤 {user_id}\n💰 {amount} сом\n🆔 {account_id}\n📅 {date}",
                reply_markup=markup)
        except:
            bot.send_message(msg.chat.id, f"🆕 ЗАЯВКА #{dep_id}\n👤 {user_id}\n💰 {amount} сом\n🆔 {account_id}\n📅 {date}", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📊 Статистика" and m.from_user.id in get_admins())
def stats(msg):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    users = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM deposits WHERE status="pending"')
    pending = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM deposits WHERE status="approved"')
    approved = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM admins')
    admins_count = c.fetchone()[0]
    conn.close()
    bot.send_message(msg.chat.id, 
        f"📊 СТАТИСТИКА\n\n"
        f"👥 Пользователей: {users}\n"
        f"👑 Админов: {admins_count}\n"
        f"⏳ В ожидании: {pending}\n"
        f"✅ Одобрено: {approved}\n"
        f"🟢 Бот: {'ВКЛЮЧЕН' if bot_active else 'ВЫКЛЮЧЕН'}")

@bot.message_handler(func=lambda m: m.text == "🖼 Изменить QR" and m.from_user.id in get_admins())
def change_qr(msg):
    bot.send_message(msg.chat.id, "🖼 Отправьте НОВЫЙ QR-код для оплаты (фото):")
    bot.register_next_step_handler(msg, save_new_qr)

def save_new_qr(msg):
    if msg.photo:
        file_id = msg.photo[-1].file_id
        save_qr(file_id)
        bot.send_message(msg.chat.id, "✅ QR-код успешно обновлен!", reply_markup=admin_menu())
    else:
        bot.send_message(msg.chat.id, "❌ Отправьте фото QR-кода!")
        bot.register_next_step_handler(msg, save_new_qr)

@bot.message_handler(func=lambda m: m.text == "🔙 Главное меню")
def back(msg):
    start(msg)

# ========== ОБРАБОТКА ЗАЯВОК (Одобрить/Отклонить) ==========
@bot.callback_query_handler(func=lambda call: True)
def handle_call(call):
    admin_id = call.from_user.id
    if admin_id not in get_admins():
        bot.answer_callback_query(call.id, "❌ Нет прав!")
        return
    
    action, dep_id = call.data.split('_')
    dep_id = int(dep_id)
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT user_id, amount FROM deposits WHERE id = ?', (dep_id,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        bot.answer_callback_query(call.id, "❌ Заявка не найдена!")
        return
    
    user_id, amount = result
    
    if action == "approve":
        update_deposit_status(dep_id, "approved")
        bot.answer_callback_query(call.id, "✅ Заявка одобрена!")
        try:
            bot.send_message(user_id, f"✅ Ваша заявка на ПОПОЛНЕНИЕ {amount} сом ОДОБРЕНА!\n\nСредства зачислены на счет.")
        except:
            pass
        try:
            bot.edit_message_caption(f"✅ ЗАЯВКА #{dep_id} ОДОБРЕНА", call.message.chat.id, call.message.message_id)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except:
            bot.edit_message_text(f"✅ ЗАЯВКА #{dep_id} ОДОБРЕНА", call.message.chat.id, call.message.message_id)
    else:
        update_deposit_status(dep_id, "rejected")
        bot.answer_callback_query(call.id, "❌ Заявка отклонена!")
        try:
            bot.send_message(user_id, f"❌ Ваша заявка на {amount} сом ОТКЛОНЕНА!\n\nПричина: чек не прошел проверку.\nСвяжитесь с поддержкой: {SUPPORT}")
        except:
            pass
        try:
            bot.edit_message_caption(f"❌ ЗАЯВКА #{dep_id} ОТКЛОНЕНА", call.message.chat.id, call.message.message_id)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except:
            bot.edit_message_text(f"❌ ЗАЯВКА #{dep_id} ОТКЛОНЕНА", call.message.chat.id, call.message.message_id)

# ========== ЗАПУСК ==========
def run_bot():
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Ошибка: {e}")
            import time
            time.sleep(5)

import threading
threading.Thread(target=run_bot, daemon=True).start()

@app.route('/')
def home():
    return "BMkassa Bot is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
