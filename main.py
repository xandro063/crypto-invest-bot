import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
import sqlite3
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Загрузка конфигурации
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ==================== БАЗА ДАННЫХ ====================
class Database:
    def __init__(self, db_name="bot_database.db"):
        self.db_name = db_name
        self.init_db()
    
    def init_db(self):
        """Создание таблиц"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        
        # Пользователи
        c.execute('''CREATE TABLE IF NOT EXISTS users
                    (user_id INTEGER PRIMARY KEY,
                     username TEXT,
                     first_name TEXT,
                     balance_available REAL DEFAULT 0,
                     balance_trading REAL DEFAULT 0,
                     total_earned REAL DEFAULT 0,
                     referrer_id INTEGER,
                     reg_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Рефералы
        c.execute('''CREATE TABLE IF NOT EXISTS referrals
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     referrer_id INTEGER,
                     referral_id INTEGER,
                     level INTEGER,
                     earned REAL DEFAULT 0)''')
        
        # Транзакции
        c.execute('''CREATE TABLE IF NOT EXISTS transactions
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER,
                     type TEXT,
                     amount REAL,
                     description TEXT,
                     date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Инвестиции
        c.execute('''CREATE TABLE IF NOT EXISTS investments
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER,
                     amount REAL,
                     start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                     unlock_date TIMESTAMP)''')
        
        conn.commit()
        conn.close()
    
    def execute(self, query, params=()):
        """Выполнение SQL-запроса"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
        conn.close()
        return c
    
    def fetchone(self, query, params=()):
        """Получение одной строки"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute(query, params)
        result = c.fetchone()
        conn.close()
        return result
    
    def fetchall(self, query, params=()):
        """Получение всех строк"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute(query, params)
        result = c.fetchall()
        conn.close()
        return result

db = Database()

# ==================== КЛАВИАТУРЫ ====================
def get_main_keyboard():
    """Основная клавиатура"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "💰 Пополнить",
        "📤 Вывести",
        "📊 Реинвестировать",
        "👥 Рефералы",
        "📋 История",
        "❓ Поддержка"
    ]
    keyboard.add(*buttons)
    return keyboard

def get_inline_menu():
    """Нижняя панель навигации"""
    keyboard = types.InlineKeyboardMarkup(row_width=4)
    buttons = [
        types.InlineKeyboardButton("🏠 Главная", callback_data="main"),
        types.InlineKeyboardButton("👥 Рефералы", callback_data="referrals"),
        types.InlineKeyboardButton("📋 История", callback_data="history"),
        types.InlineKeyboardButton("❓ Поддержка", callback_data="support")
    ]
    keyboard.add(*buttons)
    return keyboard

def get_reinvest_keyboard():
    """Клавиатура для реинвестирования"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✅ Да, реинвестировать", callback_data="reinvest_yes"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="reinvest_no")
    )
    return keyboard

# ==================== ОБРАБОТЧИКИ ====================
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Обработка команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "Пользователь"
    
    # Проверяем реферальный код
    referrer_id = None
    if len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
            # Проверяем существует ли реферер
            if not db.fetchone("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,)):
                referrer_id = None
        except:
            referrer_id = None
    
    # Добавляем пользователя в БД
    user = db.fetchone("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not user:
        db.execute(
            "INSERT INTO users (user_id, username, first_name, referrer_id) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, referrer_id)
        )
        
        # Если есть реферер, добавляем в рефералы
        if referrer_id:
            db.execute(
                "INSERT INTO referrals (referrer_id, referral_id, level) VALUES (?, ?, 1)",
                (referrer_id, user_id)
            )
            
            # Находим реферера 2-го уровня
            ref_of_ref = db.fetchone("SELECT referrer_id FROM users WHERE user_id = ?", (referrer_id,))
            if ref_of_ref and ref_of_ref[0]:
                db.execute(
                    "INSERT INTO referrals (referrer_id, referral_id, level) VALUES (?, ?, 2)",
                    (ref_of_ref[0], user_id)
                )
    
    # Приветственное сообщение
    welcome_text = (
        "🎯 *Добро пожаловать в Crypto Invest Bot!*\n\n"
        "💰 *Автоматическая торговля криптовалютой*\n"
        "📈 *Доходность: 25-35% в месяц*\n"
        "👥 *Реферальная система: 10% + 5%*\n\n"
        "👤 Ваш ID: `{}`\n"
        "🔗 Для приглашений: `https://t.me/{}?start={}`"
    ).format(
        user_id,
        (await bot.me).username,
        user_id
    )
    
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())
    
    # Нижняя панель
    await message.answer("👇 *Выберите раздел:*", parse_mode="Markdown", reply_markup=get_inline_menu())

@dp.callback_query_handler(text="main")
async def show_main(callback_query: types.CallbackQuery):
    """Главная страница с балансами"""
    user_id = callback_query.from_user.id
    
    # Получаем данные пользователя
    user = db.fetchone(
        "SELECT balance_available, balance_trading, total_earned FROM users WHERE user_id = ?",
        (user_id,)
    )
    
    if user:
        balance_available = user[0] or 0
        balance_trading = user[1] or 0
        total_earned = user[2] or 0
        
        # Получаем активные инвестиции
        investments = db.fetchall(
            "SELECT unlock_date FROM investments WHERE user_id = ? AND unlock_date > ?",
            (user_id, datetime.now())
        )
        
        days_left = "0"
        if investments:
            # Находим ближайшую дату разблокировки
            dates = [datetime.strptime(inv[0], '%Y-%m-%d %H:%M:%S') for inv in investments if inv[0]]
            if dates:
                nearest = min(dates)
                days_left = str(max(0, (nearest - datetime.now()).days))
        
        main_text = (
            "🏠 *Главное меню*\n\n"
            "👤 Ваш ID: `{}`\n"
            "💼 *Доступный баланс:* `${:.2f}`\n"
            "📈 *Торговый баланс:* `${:.2f}`\n"
            "🎯 *Всего заработано:* `${:.2f}`\n"
            "⏳ *Дней до разблокировки:* {}\n\n"
            "*Доступный баланс* — можно вывести сразу\n"
            "*Торговый баланс* — разблокируется через 20 дней"
        ).format(user_id, balance_available, balance_trading, total_earned, days_left)
        
        await callback_query.message.edit_text(main_text, parse_mode="Markdown", reply_markup=get_inline_menu())
    
    await callback_query.answer()

@dp.callback_query_handler(text="referrals")
async def show_referrals(callback_query: types.CallbackQuery):
    """Страница рефералов"""
    user_id = callback_query.from_user.id
    
    # Получаем рефералов
    level1 = db.fetchall(
        "SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND level = 1",
        (user_id,)
    )
    level2 = db.fetchall(
        "SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND level = 2",
        (user_id,)
    )
    
    level1_count = level1[0][0] if level1 else 0
    level2_count = level2[0][0] if level2 else 0
    
    # Заработано с рефералов
    earned = db.fetchone(
        "SELECT SUM(earned) FROM referrals WHERE referrer_id = ?",
        (user_id,)
    )
    earned_total = earned[0] if earned and earned[0] else 0
    
    ref_text = (
        "👥 *Реферальная система*\n\n"
        "🔗 *Ваша реферальная ссылка:*\n"
        "`https://t.me/{}?start={}`\n\n"
        "💰 *Проценты:*\n"
        "• 1-й уровень: *10%* с пополнения\n"
        "• 2-й уровень: *5%* с пополнения\n\n"
        "📊 *Статистика:*\n"
        "• Рефералов 1-го уровня: *{}*\n"
        "• Рефералов 2-го уровня: *{}*\n"
        "• Заработано с рефералов: *${:.2f}*"
    ).format((await bot.me).username, user_id, level1_count, level2_count, earned_total)
    
    await callback_query.message.edit_text(ref_text, parse_mode="Markdown", reply_markup=get_inline_menu())
    await callback_query.answer()

@dp.callback_query_handler(text="history")
async def show_history(callback_query: types.CallbackQuery):
    """История операций"""
    user_id = callback_query.from_user.id
    
    # Получаем последние 10 транзакций
    transactions = db.fetchall(
        "SELECT type, amount, description, date FROM transactions WHERE user_id = ? ORDER BY date DESC LIMIT 10",
        (user_id,)
    )
    
    if transactions:
        history_text = "📋 *История операций*\n\n"
        
        for i, trans in enumerate(transactions, 1):
            trans_type = trans[0]
            amount = trans[1]
            description = trans[2] or ""
            date = trans[3].split()[0] if ' ' in str(trans[3]) else str(trans[3])
            
            # Иконки для типов транзакций
            icons = {
                'deposit': '📥',
                'withdraw': '📤',
                'investment': '💰',
                'daily': '📈',
                'referral': '👥'
            }
            
            icon = icons.get(trans_type, '📝')
            sign = "+" if amount > 0 else ""
            history_text += f"{icon} *{date}*: {description}\n`{sign}{amount:.2f}$`\n\n"
    else:
        history_text = "📭 *У вас пока нет операций*\n\nСовершите первую операцию!"
    
    await callback_query.message.edit_text(history_text, parse_mode="Markdown", reply_markup=get_inline_menu())
    await callback_query.answer()

@dp.callback_query_handler(text="support")
async def show_support(callback_query: types.CallbackQuery):
    """Страница поддержки"""
    support_text = (
        "❓ *Поддержка*\n\n"
        "📞 *Связь с поддержкой:* @support_contact\n\n"
        "*Частые вопросы:*\n\n"
        "1. *Как пополнить баланс?*\n"
        "→ Нажмите '💰 Пополнить' и следуйте инструкциям\n\n"
        "2. *Когда можно вывести средства?*\n"
        "→ С доступного баланса - сразу\n"
        "→ С торгового - через 20 дней\n\n"
        "3. *Как работает реферальная система?*\n"
        "→ 10% с пополнения реферала 1-го уровня\n"
        "→ 5% с пополнения реферала 2-го уровня\n\n"
        "4. *Какая доходность?*\n"
        "→ 25-35% в месяц от торгового баланса"
    )
    
    await callback_query.message.edit_text(support_text, parse_mode="Markdown", reply_markup=get_inline_menu())
    await callback_query.answer()

@dp.message_handler(text="📊 Реинвестировать")
async def reinvest_request(message: types.Message):
    """Запрос на реинвестирование"""
    user_id = message.from_user.id
    
    # Проверяем доступный баланс
    user = db.fetchone("SELECT balance_available FROM users WHERE user_id = ?", (user_id,))
    
    if user and user[0] > 0:
        confirm_text = (
            "⚠️ *Подтверждение реинвестирования*\n\n"
            "Сумма: *${:.2f}*\n\n"
            "После реинвестирования:\n"
            "• Деньги перейдут в торговый баланс\n"
            "• Будут заблокированы на 20 дней\n"
            "• Начнут приносить ежедневный процент\n\n"
            "Вы уверены?"
        ).format(user[0])
        
        await message.answer(confirm_text, parse_mode="Markdown", reply_markup=get_reinvest_keyboard())
    else:
        await message.answer("❌ *На доступном балансе нет средств*", parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data.startswith('reinvest_'))
async def process_reinvest(callback_query: types.CallbackQuery):
    """Обработка реинвестирования"""
    user_id = callback_query.from_user.id
    action = callback_query.data
    
    if action == 'reinvest_yes':
        # Получаем текущий баланс
        user = db.fetchone("SELECT balance_available FROM users WHERE user_id = ?", (user_id,))
        
        if user and user[0] > 0:
            amount = user[0]
            
            # Переводим из доступного в торговый
            db.execute(
                "UPDATE users SET balance_available = 0, balance_trading = balance_trading + ? WHERE user_id = ?",
                (amount, user_id)
            )
            
            # Создаем инвестицию
            unlock_date = datetime.now() + timedelta(days=20)
            db.execute(
                "INSERT INTO investments (user_id, amount, unlock_date) VALUES (?, ?, ?)",
                (user_id, amount, unlock_date.strftime('%Y-%m-%d %H:%M:%S'))
            )
            
            # Логируем транзакцию
            db.execute(
                "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, 'investment', ?, ?)",
                (user_id, amount, 'Реинвестирование')
            )
            
            await callback_query.message.edit_text(
                "✅ *Успешно реинвестировано!*\n\n"
                f"Сумма: *${amount:.2f}*\n"
                "📅 Дата разблокировки: *{}*\n\n"
                "Деньги начали работать!".format(unlock_date.strftime('%d.%m.%Y')),
                parse_mode="Markdown",
                reply_markup=get_inline_menu()
            )
    
    elif action == 'reinvest_no':
        await callback_query.message.edit_text(
            "❌ *Реинвестирование отменено*",
            parse_mode="Markdown",
            reply_markup=get_inline_menu()
        )
    
    await callback_query.answer()

# ==================== АДМИН ПАНЕЛЬ ====================
@dp.message_handler(commands=['admin'])
async def admin_panel(message: types.Message):
    """Админ панель"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к админ-панели")
        return
    
    admin_text = (
        "👨‍💻 *Админ-панель*\n\n"
        "*Доступные команды:*\n"
        "• /stats - Статистика бота\n"
        "• /user [ID] - Инфо о пользователе\n"
        "• /bonus [ID] [сумма] - Начислить бонус\n"
        "• /daily - Начислить % всем\n"
        "• /broadcast [текст] - Рассылка"
    )
    
    await message.answer(admin_text, parse_mode="Markdown")

@dp.message_handler(commands=['stats'])
async def admin_stats(message: types.Message):
    """Статистика бота"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    # Общая статистика
    total_users = db.fetchone("SELECT COUNT(*) FROM users")[0]
    total_balance = db.fetchone("SELECT SUM(balance_available + balance_trading) FROM users")[0] or 0
    total_invested = db.fetchone("SELECT SUM(balance_trading) FROM users")[0] or 0
    
    # Последние 5 пользователей
    recent_users = db.fetchall("SELECT user_id, username, reg_date FROM users ORDER BY reg_date DESC LIMIT 5")
    
    stats_text = (
        "📊 *Статистика бота*\n\n"
        "👥 Всего пользователей: *{}*\n"
        "💰 Общий баланс: *${:.2f}*\n"
        "📈 В инвестициях: *${:.2f}*\n\n"
        "📝 *Последние регистрации:*\n"
    ).format(total_users, total_balance, total_invested)
    
    for user in recent_users:
        user_id = user[0]
        username = f"@{user[1]}" if user[1] else "Без username"
        date = user[2].split()[0] if ' ' in str(user[2]) else str(user[2])
        stats_text += f"• ID: `{user_id}` | {username} | {date}\n"
    
    await message.answer(stats_text, parse_mode="Markdown")

@dp.message_handler(commands=['daily'])
async def add_daily_profit(message: types.Message):
    """Начислить ежедневный процент"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    # Получаем всех пользователей с торговым балансом
    users = db.fetchall("SELECT user_id, balance_trading FROM users WHERE balance_trading > 0")
    
    total_added = 0
    for user in users:
        user_id = user[0]
        trading_balance = user[1]
        
        # 1% в день
        daily_profit = trading_balance * 0.01
        
        # Добавляем к доступному балансу
        db.execute(
            "UPDATE users SET balance_available = balance_available + ?, total_earned = total_earned + ? WHERE user_id = ?",
            (daily_profit, daily_profit, user_id)
        )
        
        # Логируем
        db.execute(
            "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, 'daily', ?, 'Ежедневный процент')",
            (user_id, daily_profit)
        )
        
        total_added += daily_profit
    
    await message.answer(
        "✅ *Ежедневный процент начислен*\n\n"
        f"Всего начислено: *${total_added:.2f}*\n"
        f"Пользователям: *{len(users)}*",
        parse_mode="Markdown"
    )

# ==================== ЗАПУСК БОТА ====================
if __name__ == '__main__':
    print("🤖 Бот запускается...")
    print(f"👨‍💻 Админы: {ADMIN_IDS}")
    
    # Создаем базу данных
    db.init_db()
    
    # Запускаем бота
    executor.start_polling(dp, skip_updates=True)
