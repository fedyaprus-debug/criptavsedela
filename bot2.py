import asyncio
import sqlite3
import requests
import logging
import matplotlib.pyplot as plt
from io import BytesIO
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
from aiogram.fsm.storage.memory import MemoryStorage

# =====================================================
# 1. НАСТРОЙКИ
# =====================================================
API_TOKEN = '8057360496:AAEpu3JMqWjPiYdpWfLmWpVS8KP63rv2v3A' 
logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

POPULAR_LIST = ["BTC", "ETH", "SOL", "TON", "BNB"]

# =====================================================
# 2. БАЗА ДАННЫХ
# =====================================================
def db_manage(query, params=(), fetch=False):
    conn = sqlite3.connect('crypto_storage.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS alerts 
                      (id INTEGER PRIMARY KEY, uid INTEGER, coin TEXT, buy REAL, target REAL)''')
    cursor.execute(query, params)
    data = cursor.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return data

# =====================================================
# 3. ФУНКЦИИ БИРЖИ
# =====================================================
def get_crypto_data(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}USDT"
        res = requests.get(url, timeout=5).json()
        return float(res['price'])
    except:
        return None

def generate_chart(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}USDT&interval=1h&limit=24"
        res = requests.get(url).json()
        closes = [float(c[4]) for c in res]
        plt.figure(figsize=(8, 4))
        plt.plot(closes, color='#00ff00', linewidth=2)
        plt.fill_between(range(len(closes)), closes, color='#00ff00', alpha=0.1)
        plt.title(f"{symbol}/USDT - 24h Trend")
        plt.axis('off')
        buf = BytesIO()
        plt.savefig(buf, format='png', transparent=True)
        buf.seek(0)
        plt.close()
        return buf
    except:
        return None

# =====================================================
# 4. КЛАВИАТУРЫ
# =====================================================
main_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔥 Популярные"), KeyboardButton(text="📊 Мой портфель")],
    [KeyboardButton(text="➕ Добавить"), KeyboardButton(text="🗑 Очистить всё")],
    [KeyboardButton(text="❓ Помощь")]
], resize_keyboard=True)

popular_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📈 BTC"), KeyboardButton(text="📈 ETH"), KeyboardButton(text="📈 SOL")],
    [KeyboardButton(text="📈 TON"), KeyboardButton(text="📈 BNB")],
    [KeyboardButton(text="⬅️ Назад")]
], resize_keyboard=True)

# =====================================================
# 5. ОБРАБОТЧИКИ
# =====================================================

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    db_manage("SELECT 1")
    await m.answer(f"Привет, {m.from_user.first_name}! Бот обновлен и готов к работе.", reply_markup=main_kb)

@dp.message(F.text == "🔥 Популярные")
async def show_popular(m: types.Message):
    await m.answer("Выберите монету для быстрой проверки:", reply_markup=popular_kb)

@dp.message(F.text == "⬅️ Назад")
async def go_back(m: types.Message):
    await m.answer("Главное меню", reply_markup=main_kb)

@dp.message(F.text == "🗑 Очистить всё")
async def clear_portfolio(m: types.Message):
    db_manage("DELETE FROM alerts WHERE uid = ?", (m.from_user.id,))
    await m.answer("🧹 Ваш список слежки полностью очищен.")

@dp.message(F.text == "➕ Добавить")
async def add_instr(m: types.Message):
    await m.answer("Пришли: `СИМВОЛ ЦЕНА_КУПЛИ ЦЕЛЬ` (например: `SOL 145 200`)", parse_mode="Markdown")

@dp.message(F.text == "📊 Мой портфель")
async def show_portfolio(m: types.Message):
    orders = db_manage("SELECT coin, buy, target FROM alerts WHERE uid = ?", (m.from_user.id,), fetch=True)
    if not orders:
        return await m.answer("У вас пока нет активных целей.")
    
    msg = "🔎 **Ваш мониторинг:**\n\n"
    for coin, buy, target in orders:
        now = get_crypto_data(coin)
        p = ((now - buy) / buy * 100) if now else 0
        msg += f"✅ **{coin}**: Куплен по ${buy} → Цель ${target}\n💰 Текущая: ${now} ({p:+.2f}%)\n\n"
    await m.answer(msg, parse_mode="Markdown")

@dp.message(F.text.startswith("📈 "))
async def quick_check(m: types.Message):
    sym = m.text.replace("📈 ", "").upper()
    now = get_crypto_data(sym)
    if not now:
        return await m.answer("❌ Ошибка получения цены.")

    chart = generate_chart(sym)
    caption = f"📊 **{sym}/USDT**\nЦена сейчас: `${now}`"
    
    # Проверка на наличие в портфеле
    user_data = db_manage("SELECT buy, target FROM alerts WHERE uid = ? AND coin = ?", (m.from_user.id, sym), fetch=True)
    if user_data:
        b, t = user_data[0]
        profit = ((now - b) / b) * 100
        caption += f"\n\n📍 Твой статус:\nВход: `${b}` | Цель: `${t}`\nПрофит: `{profit:+.2f}%`"

    if chart:
        await m.answer_photo(BufferedInputFile(chart.read(), filename="c.png"), caption=caption, parse_mode="Markdown")
    else:
        await m.answer(caption, parse_mode="Markdown")

@dp.message(F.text == "❓ Помощь")
async def help_cmd(m: types.Message):
    await m.answer("Как пользоваться:\n1. Нажми '➕ Добавить'\n2. Напиши `TON 5.2 10`\n"
                   "Бот запомнит цену входа и напишет тебе, когда цена достигнет цели!")

@dp.message(F.text.regexp(r'^[A-Za-z0-9]+\s+\d+\.?\d*\s+\d+\.?\d*$'))
async def process_new_coin(m: types.Message):
    try:
        sym, b, t = m.text.split()
        sym, b, t = sym.upper(), float(b), float(t)
        curr = get_crypto_data(sym)
        if not curr: return await m.answer("❌ Монета не найдена на бирже.")

        db_manage("INSERT INTO alerts (uid, coin, buy, target) VALUES (?, ?, ?, ?)", (m.from_user.id, sym, b, t))
        chart = generate_chart(sym)
        profit = ((curr - b) / b) * 100
        caption = f"🚀 **Слежка включена!**\n\nМонета: {sym}\nВход: ${b}\nЦель: ${t}\nПрофит сейчас: {profit:+.2f}%"
        
        if chart:
            await m.answer_photo(BufferedInputFile(chart.read(), filename="c.png"), caption=caption, parse_mode="Markdown")
        else:
            await m.answer(caption, parse_mode="Markdown")
    except:
        await m.answer("⚠️ Ошибка. Формат: `BTC 60000 70000`")

# =====================================================
# 6. ФОНОВАЯ ПРОВЕРКА ЦЕН
# =====================================================
async def price_checker():
    while True:
        try:
            all_alerts = db_manage("SELECT id, uid, coin, buy, target FROM alerts", fetch=True)
            for aid, uid, coin, buy, target in all_alerts:
                now = get_crypto_data(coin)
                if now and now >= target:
                    prof = ((now - buy) / buy) * 100
                    await bot.send_message(uid, f"🔔 **ЦЕЛЬ ДОСТИГНУТА!**\n\n{coin} вырос до **${now}**!\nВаш профит: **+{prof:.2f}%** 🔥")
                    db_manage("DELETE FROM alerts WHERE id = ?", (aid,))
        except Exception as e:
            logging.error(f"Ошибка чекера: {e}")
        await asyncio.sleep(30)

async def main():
    asyncio.create_task(price_checker())
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass