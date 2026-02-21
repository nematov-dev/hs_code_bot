import os
import logging
import asyncio
import psycopg2
from datetime import datetime, timedelta
import json

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from groq import Groq
from decouple import config

# ==========================================
# SOZLAMALAR
# ==========================================
BOT_TOKEN = config("BOT_TOKEN")
GROQ_API_KEY = config("GROQ_API_KEY")
ADMIN_ID = config("ADMIN_ID", cast=int)

DB_CONFIG = {
    "dbname": config("DB_NAME"),
    "user": config("DB_USER"),
    "password": config("DB_PASSWORD"),
    "host": config("DB_HOST"),
    "port": config("DB_PORT", cast=int)
}

# Groq mijozini sozlash
client = Groq(api_key=GROQ_API_KEY)

logging.basicConfig(level=logging.INFO)

# ==========================================
# MA'LUMOTLAR BAZASI
# ==========================================
def init_db():
    conn = psycopg2.connect(**DB_CONFIG); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users_hs (
            user_id BIGINT PRIMARY KEY,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_premium BOOLEAN DEFAULT FALSE,
            sub_end_date TIMESTAMP DEFAULT NULL,
            requests_today INTEGER DEFAULT 0,
            last_request_date DATE DEFAULT CURRENT_DATE
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            id SERIAL PRIMARY KEY,
            daily_limit INTEGER DEFAULT 10
        );
    """)
    cur.execute("INSERT INTO bot_settings (id, daily_limit) VALUES (1, 10) ON CONFLICT DO NOTHING;")
    conn.commit(); cur.close(); conn.close()

init_db()

# ==========================================
# YORDAMCHI FUNKSIYALAR
# ==========================================
def get_limit():
    conn = psycopg2.connect(**DB_CONFIG); cur = conn.cursor()
    cur.execute("SELECT daily_limit FROM bot_settings WHERE id = 1")
    res = cur.fetchone()[0]
    cur.close(); conn.close()
    return res

async def get_user_data(user_id):
    conn = psycopg2.connect(**DB_CONFIG); cur = conn.cursor()
    cur.execute("SELECT is_premium, sub_end_date, requests_today, last_request_date FROM users_hs WHERE user_id = %s", (user_id,))
    res = cur.fetchone()
    if not res:
        cur.execute("INSERT INTO users_hs (user_id) VALUES (%s)", (user_id,))
        conn.commit()
        res = (False, None, 0, datetime.now().date())
    cur.close(); conn.close()
    return res

# ==========================================
# STATES
# ==========================================
class Form(StatesGroup):
    ai_ask = State()
    admin_mail = State()
    admin_limit = State()
    admin_sub_id = State()

# ==========================================
# BOT BOSHQARUVI
# ==========================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Form.ai_ask, F.text == "🚫 Bekor qilish")
async def cancel_ai(message: types.Message, state: FSMContext):
    await state.clear()
    
    # Asosiy menyu tugmalarini qaytarish
    kb = [
        [KeyboardButton(text="🤖 AI Agentga so'rov")],
        [KeyboardButton(text="👤 Hisobim"), KeyboardButton(text="🌟 Premium olish")],
        [KeyboardButton(text="📚 Foydali bo'lim"), KeyboardButton(text="📖 Qo'llanma")]
    ]
    if message.from_user.id == ADMIN_ID:
        kb.append([KeyboardButton(text="⚙️ Admin Panel")])
        
    await message.answer(
        "❌ AI so'rovi bekor qilindi.",
        reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    )

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    kb = [
        [KeyboardButton(text="🤖 AI Agentga so'rov")],
        [KeyboardButton(text="👤 Hisobim"), KeyboardButton(text="🌟 Premium olish")],
        [KeyboardButton(text="📚 Foydali bo'lim"), KeyboardButton(text="📖 Qo'llanma")]
    ]
    if message.from_user.id == ADMIN_ID:
        kb.append([KeyboardButton(text="⚙️ Admin Panel")])
    
    await message.answer(
        "Xush kelibsiz! Men TIF TN kodlarini aniqlovchi AI Agentman.",
        reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    )

@dp.message(F.text == "📚 Foydali bo'lim")
async def useful_section(message: types.Message):
    text = (
        "📚 **Foydali ma'lumotlar va hujjatlar bo'limi**\n\n"
        "Kerakli bo'limni tanlang, men sizga tegishli ma'lumot va PDF faylni yuboraman:"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 TIF TN Qoidalari", callback_data="useful_rules")],
        [InlineKeyboardButton(text="🔤 Qisqartmalar va Ramzlar", callback_data="useful_abbr")],
        [InlineKeyboardButton(text="⚖️ O'lchov birliklari", callback_data="useful_units")],
    ])
    
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")
from aiogram.types import FSInputFile # Fayllarni yuborish uchun kerak

@dp.callback_query(F.data.startswith("useful_"))
async def useful_callback(call: types.CallbackQuery):
    data = call.data.split("_")[1]


    try:
        if data == "rules":
            caption = "📄 **TIF TN qoidalari.**"
            file = FSInputFile("documents/qoidalar.pdf")
            await call.message.answer_document(document=file, caption=caption, parse_mode="Markdown")
            
        elif data == "abbr":
            caption = "🔤 **Qisqartmalar va ramzlar ro'yxati.**"
            file = FSInputFile("documents/qisqartmalar.pdf")
            await call.message.answer_document(document=file, caption=caption, parse_mode="Markdown")
            
        elif data == "units":
            caption = "⚖️ **TIF TN o'lchov birliklari.**"
            file = FSInputFile("documents/birliklar.pdf")
            await call.message.answer_document(document=file, caption=caption, parse_mode="Markdown")
            
    except Exception as e:
        logging.error(f"Fayl yuborishda xatolik: {e}")
        await call.message.answer("❌ Kechirasiz, faylni yuklashda xatolik yuz berdi. Texnik bo'limga xabar berildi.")
    
    await call.answer()


@dp.message(F.text == "📖 Qo'llanma")
async def manual_cmd(message: types.Message):
    text = (
        "📘 **Botdan foydalanish yo'riqnomasi:**\n\n"
        "1. **🤖 AI Agentga so'rov'** tugmasini bosing.\n"
        "2. Mahsulot nomini, modelini va xususiyatlarini yozing.\n"
        "3. AI sizga TIF TN kodi va tavsifni taqdim etadi.\n\n"
        "⚠️ **DIQQAT:**\n"
        "Bot tomonidan taqdim etilgan TIF TN kodlari va ma'lumotlar **faqat tavsiya sifatida** taqdim etiladi. "
        "Bojxona rasmiylashtiruvi jarayonida xatoliklarga yo'l qo'ymaslik uchun, ma'lumotlarni rasmiy "
        "bojxona organlari ma'lumotlari orqali qayta tekshirib ko'rishingizni so'raymiz.\n\n"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🌟 Premium olish")
async def manual_cmd(message: types.Message):
    text = (
        "📘 **Premium olish uchun admin bilan bog'laning: @ZufarNurmatov**\n\n"
        )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "👤 Hisobim")
async def profile(message: types.Message):
    is_prem, sub_end, req_today, last_date = await get_user_data(message.from_user.id)
    limit = get_limit()
    status = "🌟 Premium" if is_prem else "🆓 Tekin"
    rem = "Cheksiz" if is_prem else f"{req_today}/{limit}"
    
    text = (f"🆔 ID: `{message.from_user.id}`\n"
            f"📊 Tarif: {status}\n"
            f"🔄 Bugungi so'rovlar: {rem}")
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🤖 AI Agentga so'rov")
async def ai_start(message: types.Message, state: FSMContext):
    is_prem, _, req_today, last_date = await get_user_data(message.from_user.id)
    limit = get_limit()
    
    if not is_prem and last_date == datetime.now().date() and req_today >= limit:
        await message.answer("⚠️ Bugungi bepul limitingiz tugadi. Premiumga o'ting!")
        return
        
    await state.set_state(Form.ai_ask)
    
    # Bekor qilish tugmasini yaratish
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🚫 Bekor qilish")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await message.answer(
        "Mahsulotingizni batafsil yozing:\n\n"
        "Jarayonni to'xtatish uchun pastdagi tugmani bosing.",
        reply_markup=cancel_kb
    )


@dp.message(Form.ai_ask)
async def ai_handler(message: types.Message, state: FSMContext):
    wait = await message.answer("🔍 Tahlil qilinmoqda...")
    current_year = datetime.now().year
    
    system_prompt = (
        "Siz O'zbekiston Respublikasi professional bojxona deklarantisiz. "
        "Foydalanuvchi mahsuloti uchun TIF TN kodini ierarxik (ota koddan sub-kodgacha) aniqlang. "
        f"Foydalanuvchi mahsuloti uchun {current_year}-yilgi TIF TN tasniflagichi bo'yicha "        "Javobni FAQAT quyidagi JSON formatida qaytaring (o'zbek tilida): "
        "{"
        '  "ierarxiya": ['
        '    {"daraja": "Guruh (2 raqam)", "kod": "kod", "tavsif": "tavsif"},'
        '    {"daraja": "Pozitsiya (4 raqam)", "kod": "kod", "tavsif": "tavsif"},'
        '    {"daraja": "Sub-pozitsiya (10 raqam)", "kod": "kod", "tavsif": "tavsif"}'
        '  ],'
        '  "olchov_birligi": "dona/kg/..." '
        "}"
    )

    try:
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Mahsulot: {message.text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        res_content = completion.choices[0].message.content
        data = json.loads(res_content)
        
        # Ierarxik matnni shakllantirish
        hierarchy_text = ""
        for item in data.get('ierarxiya', []):
            hierarchy_text += f"🔹 **{item['daraja']}**: `{item['kod']}`\n└ {item['tavsif']}\n\n"
        
        result_text = (
            f"📦 **Mahsulot:** {message.text}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"{hierarchy_text}"
            f"📏 **O‘lchov birligi:** {data.get('olchov_birligi')}\n"
            f"━━━━━━━━━━━━━━━"
        )

        # Baza bilan ishlash (Limitni yangilash)
        conn = psycopg2.connect(**DB_CONFIG); cur = conn.cursor()
        cur.execute("UPDATE users_hs SET requests_today = requests_today + 1 WHERE user_id = %s", (message.from_user.id,))
        conn.commit(); cur.close(); conn.close()
        
        await wait.delete()
        await message.answer(result_text, parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        logging.error(f"Ierarxiya xatosi: {e}")
        await wait.edit_text("❌ Ma'lumot topilmadi yoki ierarxik tahlilda xatolik yuz berdi.")
    
# ==========================================
# ADMIN PANEL (Statistika va Boshqaruv)
# ==========================================
@dp.message(F.text == "⚙️ Admin Panel", F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    conn = psycopg2.connect(**DB_CONFIG); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users_hs")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users_hs WHERE is_premium = TRUE")
    prems = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users_hs WHERE join_date >= CURRENT_DATE")
    today = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users_hs WHERE join_date >= CURRENT_DATE - INTERVAL '7 days'")
    week = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users_hs WHERE join_date >= CURRENT_DATE - INTERVAL '30 days'")
    month = cur.fetchone()[0]
    cur.close(); conn.close()
    
    text = (f"📊 **Statistika**\n\n"
            f"👥 Jami: `{total}` | 🌟 Premium: `{prems}`\n"
            f"🆓 Oddiy: `{total - prems}`\n\n"
            f"📈 **Yangi userlar:**\n"
            f"📅 Bugun: `{today}`\n"
            f"🗓 Hafta: `{week}`\n"
            f"🌙 Oy: `{month}`\n\n"
            f"⚙️ Limit: `{get_limit()}`")
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Xabar", callback_data="a_mail"), InlineKeyboardButton(text="🔢 Limit", callback_data="a_limit")],
        [InlineKeyboardButton(text="💎 Obuna berish", callback_data="a_sub")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

# Admin callbacklari (limit, mail, sub) yuqoridagi Gemini kodi bilan bir xil ishlaydi
@dp.callback_query(F.data == "a_limit", F.from_user.id == ADMIN_ID)
async def a_lim(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.admin_limit)
    await call.message.answer("Limitni son bilan kiriting:")
    await call.answer()

@dp.message(Form.admin_limit)
async def a_lim_done(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        conn = psycopg2.connect(**DB_CONFIG); cur = conn.cursor()
        cur.execute("UPDATE bot_settings SET daily_limit = %s WHERE id = 1", (int(message.text),))
        conn.commit(); cur.close(); conn.close()
        await message.answer("✅ Limit yangilandi.")
        await state.clear()

@dp.callback_query(F.data == "a_mail", F.from_user.id == ADMIN_ID)
async def a_ml(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.admin_mail)
    await call.message.answer("Xabarni yuboring:")
    await call.answer()

@dp.message(Form.admin_mail)
async def a_ml_done(message: types.Message, state: FSMContext):
    conn = psycopg2.connect(**DB_CONFIG); cur = conn.cursor()
    cur.execute("SELECT user_id FROM users_hs"); users = cur.fetchall()
    cur.close(); conn.close()
    for u in users:
        try: await bot.send_message(u[0], message.text)
        except: continue
    await message.answer("✅ Xabar yuborildi.")
    await state.clear()

@dp.callback_query(F.data == "a_sub", F.from_user.id == ADMIN_ID)
async def a_sb(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.admin_sub_id)
    await call.message.answer("Foydalanuvchi ID sini kiriting:")
    await call.answer()

@dp.message(Form.admin_sub_id)
async def a_sb_id(message: types.Message, state: FSMContext):
    await state.update_data(t_id=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 kun", callback_data="p_1"), InlineKeyboardButton(text="1 hafta", callback_data="p_7")],
        [InlineKeyboardButton(text="1 oy", callback_data="p_30"), InlineKeyboardButton(text="1 yil", callback_data="p_365")]
    ])
    await message.answer("Muddatni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("p_"))
async def a_sb_final(call: types.CallbackQuery, state: FSMContext):
    days = int(call.data.split("_")[1])
    data = await state.get_data(); t_id = int(data['t_id'])
    end_d = datetime.now() + timedelta(days=days)
    conn = psycopg2.connect(**DB_CONFIG); cur = conn.cursor()
    cur.execute("UPDATE users_hs SET is_premium = TRUE, sub_end_date = %s WHERE user_id = %s", (end_d, t_id))
    conn.commit(); cur.close(); conn.close()
    await call.message.answer(f"✅ ID {t_id} premium qilindi.")
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())