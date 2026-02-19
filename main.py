import os
import re
import pandas as pd
import logging
import asyncio
import psycopg2
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import google.generativeai as genai
from aiogram.types import FSInputFile
from decouple import config

# SOZLAMALAR
BOT_TOKEN = config("BOT_TOKEN")
GEMINI_API_KEY = config("GEMINI_API_KEY")
ADMIN_ID = config("ADMIN_ID", cast=int)
CSV_FILE = "documents/hs_codes_uz.csv"

DB_CONFIG = {
    "dbname": config("DB_NAME"),
    "user": config("DB_USER"),
    "password": config("DB_PASSWORD"),
    "host": config("DB_HOST"),
    "port": config("DB_PORT", cast=int)
}

genai.configure(api_key=GEMINI_API_KEY)
# Model nomi to'g'irlandi (gemini-2.5 mavjud emas, 1.5-flash ishlatildi)
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

logging.basicConfig(level=logging.INFO)

# MAXSUS FUNKSIYALAR
def escape_md(text):
    """MarkdownV2 uchun barcha maxsus belgilarni to'suvchi funksiya"""
    if text is None: return ""
    # MarkdownV2 uchun barcha rezerv qilingan belgilar:
    parse_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(parse_chars)}])', r'\\\1', str(text))

def get_dynamic_pattern(query):
    q = query.lower().replace('к', '[кх]').replace('х', '[кх]')
    return rf"(?:^|\s|\b){q}(?:лар|li|idagi|ning|ni|ga|lari)?(?:\b|\s|$)"

def to_cyrillic(text):
    mapping = {"sh": "ш", "ch": "ч", "yo'": "йў", "yo": "ё", "yu": "ю", "ya": "я", "ye": "е", "o'": "ў", "g'": "ғ", "a": "а", "b": "б", "v": "в", "g": "г", "d": "д", "e": "е", "j": "ж", "z": "з", "i": "и", "y": "й", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "r": "р", "s": "с", "t": "т", "u": "у", "f": "ф", "x": "х", "h": "ҳ", "q": "қ", "ts": "ц"}
    text = text.lower()
    for lat, cyr in mapping.items(): text = text.replace(lat, cyr)
    return text

# MA'LUMOTLAR BAZASI
def init_db():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users_hs (
                user_id BIGINT PRIMARY KEY,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_premium BOOLEAN DEFAULT FALSE,
                sub_end_date TIMESTAMP DEFAULT NULL
            );
        """)
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        logging.error(f"Baza xatosi: {e}")

init_db()

# MIDDLEWARE
class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if not user: return await handler(event, data)
        
        conn = psycopg2.connect(**DB_CONFIG); cur = conn.cursor()
        cur.execute("SELECT is_premium, sub_end_date FROM users_hs WHERE user_id = %s", (user.id,))
        res = cur.fetchone()
        
        if not res:
            cur.execute("INSERT INTO users_hs (user_id) VALUES (%s)", (user.id,))
            conn.commit()
            is_premium, sub_end_date = False, None
        else:
            is_premium, sub_end_date = res

        if is_premium and sub_end_date and sub_end_date < datetime.now():
            cur.execute("UPDATE users_hs SET is_premium = FALSE WHERE user_id = %s", (user.id,))
            conn.commit()
            is_premium = False

        cur.close(); conn.close()
        
        if isinstance(event, types.Message) and event.text == "🤖 AI qidiruv":
            if user.id != ADMIN_ID and not is_premium:
                # Xabar escape qilindi
                await event.answer(escape_md("⚠️ AI qidiruv faqat Premium foydalanuvchilar uchun!\nPremium olish uchun admin bilan bog'laning: @ZufarNurmatov"), parse_mode="MarkdownV2")
                return
        
        return await handler(event, data)

# CSV YUKLASH
try:
    df = pd.read_csv(CSV_FILE)
    df = df.iloc[:, [0, 1, 2]] 
    df.columns = ['code', 'description', 'unity']
    df['clean_code'] = df['code'].astype(str).str.replace(r'\D', '', regex=True)
except Exception as e:
    logging.error(f"CSV xatosi: {e}")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.message.middleware(SubscriptionMiddleware())

class Form(StatesGroup):
    by_name = State()
    by_code = State()
    by_ai = State()
    admin_give_id = State()

# SEND_RESULTS
async def send_results(message_obj, query, page, s_type):
    items_per_page = 5
    start_idx = page * items_per_page
    
    if s_type == "name":
        pattern = f"(?:{get_dynamic_pattern(query)})|(?:{get_dynamic_pattern(to_cyrillic(query))})"
        mask = df['description'].astype(str).str.contains(pattern, case=False, na=False, regex=True)
        filtered_indices = df.index[mask].tolist()
    else: 
        mask = df['clean_code'].str.startswith(query)
        filtered_indices = df.index[mask].tolist()

    if not filtered_indices:
        text = escape_md("❌ Hech narsa topilmadi.")
        if isinstance(message_obj, types.Message): await message_obj.answer(text, parse_mode="MarkdownV2")
        else: await message_obj.message.edit_text(text, parse_mode="MarkdownV2")
        return

    current_batch = filtered_indices[start_idx : start_idx + items_per_page]
    res_count = len(filtered_indices)
    text = f"🔍 *Natijalar:* `{res_count}` ta \(Sahifa: `{page+1}`\)\n"

    for idx in current_batch:
        row = df.iloc[idx]
        code, description = str(row['code']), str(row['description'])
        clean_code = str(row['clean_code'])
        unity = str(row['unity']) if pd.notna(row['unity']) else "-"

        if len(clean_code) < 4: continue

        item_text = f"{escape_md('-' * 25)}\n"
        item_text += f"🔢 *KOD:* `{escape_md(code)}`\n"
        item_text += f"📝 *TASNIF:* {escape_md(description)}\n"
        if len(clean_code) == 10:
            item_text += f"📌 *BIRLIK:* `{escape_md(unity)}`\n"
        text += item_text

    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.add(InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"prev_{s_type}_{query}_{page}"))
    if len(filtered_indices) > start_idx + items_per_page:
        builder.add(InlineKeyboardButton(text="Oldinga ➡️", callback_data=f"next_{s_type}_{query}_{page}"))
    
    # Xabar hajmini tekshirish
    if len(text) > 4000: text = text[:4000] + "\.\.\."

    try:
        if isinstance(message_obj, types.Message): 
            await message_obj.answer(text, parse_mode="MarkdownV2", reply_markup=builder.as_markup())
        else: 
            await message_obj.message.edit_text(text, parse_mode="MarkdownV2", reply_markup=builder.as_markup())
    except Exception as e:
        logging.error(f"TG Send Error: {e}")

# HANDLERLAR
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    kb = [[KeyboardButton(text="🔎 Nom bo'yicha"), KeyboardButton(text="🔢 Kod bo'yicha")],
          [KeyboardButton(text="🤖 AI qidiruv"), KeyboardButton(text="👤 Hisobim")],
          [KeyboardButton(text="📗 Foydali bo'lim")]]
    if message.from_user.id == ADMIN_ID: kb.append([KeyboardButton(text="⚙️ Admin Panel")])
    await message.answer(escape_md("TIF TN kodlarini qidirish botiga xush kelibsiz!"), 
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True), parse_mode="MarkdownV2")

@dp.message(F.text == "👤 Hisobim")
async def profile(message: types.Message):
    conn = psycopg2.connect(**DB_CONFIG); cur = conn.cursor()
    cur.execute("SELECT is_premium, sub_end_date FROM users_hs WHERE user_id = %s", (message.from_user.id,))
    res = cur.fetchone(); cur.close(); conn.close()
    status = "🌟 Premium" if res and res[0] else "🆓 Tekin"
    date_str = escape_md(res[1].strftime('%d.%m.%Y %H:%M')) if res and res[1] else "Mavjud emas"
    text = (f"🆔 *ID:* `{message.from_user.id}`\n"
            f"📊 *Tarif:* {status}\n"
            f"📅 *Muddati:* {date_str}")
    await message.answer(text, parse_mode="MarkdownV2")

@dp.message(F.text == "🔎 Nom bo'yicha")
async def n_q(message: types.Message, state: FSMContext): 
    await state.set_state(Form.by_name)
    await message.answer("🔍 Mahsulot nomini kiriting:")

@dp.message(Form.by_name)
async def n_h(message: types.Message, state: FSMContext): 
    await send_results(message, message.text, 0, "name")
    await state.clear()

@dp.message(F.text == "🔢 Kod bo'yicha")
async def c_q(message: types.Message, state: FSMContext): 
    await state.set_state(Form.by_code)
    await message.answer("🔢 Kodning raqamlarini kiriting:")

@dp.message(Form.by_code)
async def c_h(message: types.Message, state: FSMContext):
    clean_query = re.sub(r'\D', '', message.text)
    if clean_query: await send_results(message, clean_query, 0, "code")
    else: await message.answer("❌ Faqat raqam kiriting.")
    await state.clear()

@dp.callback_query(F.data.startswith(("next_", "prev_")))
async def pagin(call: types.CallbackQuery):
    parts = call.data.split("_")
    action, s_type, query, page = parts[0], parts[1], parts[2], int(parts[3])
    new_page = page + 1 if action == "next" else max(0, page - 1)
    await send_results(call, query, new_page, s_type)
    await call.answer()

# AI QIDIRUV
@dp.message(F.text == "🤖 AI qidiruv")
async def ai_q(message: types.Message, state: FSMContext): 
    await state.set_state(Form.by_ai)
    await message.answer("Mahsulotni tasvirlang (AI eng mos terminni topadi):")


@dp.message(Form.by_ai)
async def ai_h(message: types.Message, state: FSMContext):
    st = await message.answer(escape_md("🤖 AI Deklarant tahlil qilmoqda..."), parse_mode="MarkdownV2")
    try:
        # Prompt o'zgartirildi: AI endi murakkab jumla emas, bazadan topish oson bo'lgan yakka so'zlar beradi
        prompt = (
            f"Siz professional bojxona deklarantisiz. Foydalanuvchi '{message.text}' deb kiritdi. "
            f"Ushbu mahsulotni TIF TN bazasidan topish uchun 3 ta eng muhim kalit so'zni "
            f"kirill alifbosida, faqat vergul bilan ajratib yozing. "
            f"Masalan: 'Playstation' bo'lsa, 'видео ўйин, консол, ускуна' deb yozing."
        )
        response = await asyncio.to_thread(gemini_model.generate_content, prompt)
        
        if response and response.text:
            # AI dan kelgan so'zlarni massivga olamiz
            raw_keywords = response.text.strip().replace('*', '').split(',')
            keywords = [k.strip() for k in raw_keywords if len(k.strip()) > 2]
            
            found = False
            for kw in keywords:
                # get_dynamic_pattern so'zning o'zagini qidiradi
                pattern = f"(?:{get_dynamic_pattern(kw)})|(?:{get_dynamic_pattern(to_cyrillic(kw))})"
                
                # Bazadan qidirish
                mask = df['description'].astype(str).str.contains(pattern, case=False, na=False, regex=True)
                if mask.any():
                    await st.delete()
                    # Agar topilsa, o'sha kalit so'z bo'yicha natijalarni chiqaramiz
                    await send_results(message, kw, 0, "name")
                    found = True
                    break
            
            if not found:
                await st.edit_text(
                    escape_md(f"❌ AI bazadan moslik topolmadi."), 
                    parse_mode="MarkdownV2"
                )
        else:
            await st.edit_text("❌ AI tahlil qila olmadi.")
    except Exception as e:
        logging.error(f"AI Error: {e}")
        await st.edit_text("❌ Xatolik yuz berdi.")
    await state.clear()


# ADMIN PANEL
@dp.message(F.text == "⚙️ Admin Panel", F.from_user.id == ADMIN_ID)
async def admin_main(message: types.Message):
    conn = psycopg2.connect(**DB_CONFIG); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users_hs"); total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users_hs WHERE is_premium = TRUE"); premiums = cur.fetchone()[0]
    cur.close(); conn.close()

    stat_text = (f"📊 *Statistika*\n\n👥 Jami: `{total}`\n🌟 Premium: `{premiums}`")
    ikb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Obuna Berish", callback_data="adm_sub")]])
    await message.answer(stat_text, reply_markup=ikb, parse_mode="MarkdownV2")

@dp.callback_query(F.data == "adm_sub", F.from_user.id == ADMIN_ID)
async def sub_start(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.admin_give_id)
    await call.message.answer("ID kiriting:")
    await call.answer()

@dp.message(Form.admin_give_id)
async def sub_id_received(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam!")
    await state.update_data(target_id=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="30 Kun", callback_data="dur_30")]])
    await message.answer(f"ID: {message.text} uchun muddat:", reply_markup=kb)

@dp.callback_query(F.data.startswith("dur_"), F.from_user.id == ADMIN_ID)
async def sub_finish(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data(); target_id = int(data.get("target_id"))
    days = int(call.data.split("_")[1])
    
    conn = psycopg2.connect(**DB_CONFIG); cur = conn.cursor()
    new_end = datetime.now() + timedelta(days=days)
    cur.execute("UPDATE users_hs SET is_premium = TRUE, sub_end_date = %s WHERE user_id = %s", (new_end, target_id))
    conn.commit(); cur.close(); conn.close()
    
    await call.message.edit_text(escape_md(f"✅ ID {target_id} premium qilindi."), parse_mode="MarkdownV2")
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())