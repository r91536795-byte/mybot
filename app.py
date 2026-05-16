import telebot
from telebot import types
import sqlite3
import time
import os
from datetime import datetime
import threading
from flask import Flask, request, jsonify

# ========== НАСТРОЙКИ (ТОКЕН БЕРЕТСЯ ИЗ ПЕРЕМЕННЫХ RENDER) ==========
TOKEN = os.environ.get("TOKEN")
MAIN_ADMIN = int(os.environ.get("MAIN_ADMIN", "8763658506"))
SUPPORT = os.environ.get("SUPPORT", "@KONS_TZ")

# ПРОВЕРКА: если токен не найден, бот не запустится
if not TOKEN:
    print("❌ ОШИБКА: Токен не найден! Добавь переменную TOKEN в Render")
    exit(1)

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, join_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins (chat_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, account_id TEXT, status TEXT, date TEXT)''')
    c.execute('INSERT OR IGNORE INTO admins (chat_id) VALUES (?)', (MAIN_ADMIN,))
    conn.commit()
    conn.close()
    print("✅ База данных готова")

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

def add_deposit(user_id, amount, account_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('INSERT INTO deposits (user_id, amount, account_id, status, date) VALUES (?, ?, ?, ?, ?)',
              (user_id, amount, account_id, 'pending', datetime.now().strftime("%d.%m.%Y %H:%M")))
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
    c.execute('SELECT id, user_id, amount, account_id, date FROM deposits WHERE status = "pending"')
    rows = c.fetchall()
    conn.close()
    return rows

init_db()

# ========== МЕНЮ ==========
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 Пополнение", "💸 Вывод")
    markup.add("👨‍💻 Поддержка")
    if user_id in get_admins():
        markup.add("⚙️ Админ панель")
    return markup

def admin_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📋 Заявки", "📊 Статистика")
    markup.add("🔙 Главное меню")
    return markup

# ========== КОМАНДЫ БОТА ==========
@bot.message_handler(commands=['start'])
def start(msg):
    add_user(msg.chat.id)
    bot.send_message(msg.chat.id, 
        f"✨ Добро пожаловать, {msg.from_user.first_name}!\n\n🏦 BMkassa - ваш надежный финансовый помощник\n\n👇 Выберите действие:", 
        reply_markup=main_menu(msg.from_user.id))

@bot.message_handler(func=lambda m: m.text == "👨‍💻 Поддержка")
def support(msg):
    bot.send_message(msg.chat.id, f"📞 Поддержка: {SUPPORT}\n\nОтветим в течение 15 минут!")

@bot.message_handler(func=lambda m: m.text == "💰 Пополнение")
def deposit(msg):
    bot.send_message(msg.chat.id, "🆔 Введите ID счета:")
    bot.register_next_step_handler(msg, get_account_id)

def get_account_id(msg):
    account_id = msg.text
    bot.send_message(msg.chat.id, "💰 Введите сумму (от 100 до 100 000 сом):")
    bot.register_next_step_handler(msg, lambda m: get_amount(m, account_id))

def get_amount(msg, account_id):
    if not msg.text.isdigit():
        bot.send_message(msg.chat.id, "❌ Введите число!")
        return
    amount = int(msg.text)
    if amount < 100 or amount > 100000:
        bot.send_message(msg.chat.id, "❌ Сумма от 100 до 100 000 сом!")
        return
    
    dep_id = add_deposit(msg.chat.id, amount, account_id)
    
    # Отправляем админам
    admins = get_admins()
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}")
    )
    
    for admin in admins:
        try:
            bot.send_message(admin, f"🆕 НОВАЯ ЗАЯВКА #{dep_id}\n👤 Пользователь: {msg.chat.id}\n💰 Сумма: {amount} сом\n🆔 Счет: {account_id}", reply_markup=markup)
        except:
            pass
    
    bot.send_message(msg.chat.id, "✅ Заявка отправлена! Ожидайте подтверждения.")

@bot.message_handler(func=lambda m: m.text == "💸 Вывод")
def withdraw(msg):
    bot.send_message(msg.chat.id, f"💸 Для вывода средств обратитесь в поддержку: {SUPPORT}")

@bot.message_handler(func=lambda m: m.text == "⚙️ Админ панель" and m.from_user.id in get_admins())
def admin_panel(msg):
    bot.send_message(msg.chat.id, "⚙️ Админ панель", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📋 Заявки" and m.from_user.id in get_admins())
def view_requests(msg):
    deposits = get_pending_deposits()
    if not deposits:
        bot.send_message(msg.chat.id, "📭 Нет заявок")
        return
    for dep in deposits:
        dep_id, user_id, amount, account_id, date = dep
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}")
        )
        bot.send_message(msg.chat.id, f"🆕 ЗАЯВКА #{dep_id}\n👤 {user_id}\n💰 {amount} сом\n🆔 {account_id}\n📅 {date}", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📊 Статистика" and m.from_user.id in get_admins())
def stats(msg):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    users = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM deposits WHERE status="pending"')
    pending = c.fetchone()[0]
    conn.close()
    bot.send_message(msg.chat.id, f"📊 СТАТИСТИКА\n\n👥 Пользователей: {users}\n⏳ Заявок: {pending}")

@bot.message_handler(func=lambda m: m.text == "🔙 Главное меню")
def back(msg):
    start(msg)

# ========== ОБРАБОТКА ЗАЯВОК ==========
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
    user_id, amount = c.fetchone()
    conn.close()
    
    if action == "approve":
        update_deposit_status(dep_id, "approved")
        bot.answer_callback_query(call.id, "✅ Одобрено!")
        try:
            bot.send_message(user_id, f"✅ Ваша заявка на {amount} сом ОДОБРЕНА!")
        except:
            pass
        bot.edit_message_text(f"✅ ЗАЯВКА #{dep_id} ОДОБРЕНА", call.message.chat.id, call.message.message_id)
    else:
        update_deposit_status(dep_id, "rejected")
        bot.answer_callback_query(call.id, "❌ Отклонено!")
        try:
            bot.send_message(user_id, f"❌ Ваша заявка на {amount} сом ОТКЛОНЕНА! Свяжитесь с поддержкой: {SUPPORT}")
        except:
            pass
        bot.edit_message_text(f"❌ ЗАЯВКА #{dep_id} ОТКЛОНЕНА", call.message.chat.id, call.message.message_id)

# ========== FLASK ==========
@app.route('/')
def index():
    return "BMkassa Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

# ========== ЗАПУСК БОТА ==========
def run_bot():
    print("🤖 Бот BMkassa запускается...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Ошибка бота: {e}")
            time.sleep(5)

# ========== ГЛАВНЫЙ ЗАПУСК ==========
if __name__ == "__main__":
    print("🚀 Запуск BMkassa на Render...")
    print(f"📝 Токен установлен: {'✅ ДА' if TOKEN else '❌ НЕТ'}")
    
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask
    port = int(os.environ.get("PORT", 5000))
    print(f"🌐 Flask запущен на порту {port}")
    app.run(host='0.0.0.0', port=port)
