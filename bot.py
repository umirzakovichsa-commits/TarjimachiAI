import os
import re
import logging
import datetime
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaDocument
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from database import Database

# .env faylidan sozlamalarni yuklash
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Guruh ID raqamini o'qish (GROUP_CHAT_ID)
GROUP_CHAT_ID_STR = os.getenv("GROUP_CHAT_ID", "")
GROUP_CHAT_ID = None
if GROUP_CHAT_ID_STR:
    clean_str = GROUP_CHAT_ID_STR.strip()
    if clean_str.startswith("-"):
        if clean_str[1:].isdigit():
            GROUP_CHAT_ID = int(clean_str)
    elif clean_str.isdigit():
        GROUP_CHAT_ID = int(clean_str)

# Kassirlar ID raqamlarini to'plamga yuklash
CASHIER_IDS = set()
cashier_ids_str = os.getenv("CASHIER_IDS", "")
for uid in cashier_ids_str.split(","):
    uid = uid.strip()
    if uid.isdigit() or (uid.startswith("-") and uid[1:].isdigit()):
        CASHIER_IDS.add(int(uid))

# Ma'lumotlar bazasini ulash
db = Database()

# Albomlarni (media group) vaqtincha saqlash uchun lug'at
MEDIA_GROUPS = {}

# Logging sozlamalari
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# Render.com uchun Health Check Web Server
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bot ishlamoqda. OK")
        
    def log_message(self, format, *args):
        return

def run_health_check_server():
    """Render port cheklovidan o'tishi uchun alohida oqimda ishlaydigan server."""
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"Health check server {port}-portda ishga tushdi...")
    server.serve_forever()


def clean_line(text: str) -> str:
    """Qator boshidagi ortiqcha so'zlarni (Mijoz, Nakladnoy, Summa) tozalaydi."""
    cleaned = re.sub(
        r'^(?:nakladnoy|mijoz|summa|klient|xaridor|client|to\'lov|tolov|tulov|sum)\s*:?\s*', 
        '', 
        text, 
        flags=re.IGNORECASE
    )
    return cleaned.strip()

def format_amount(amount_str: str) -> str:
    """To'lov summasini chiroyli formatga keltirish."""
    if not amount_str:
        return amount_str
    
    digits = "".join([c for c in amount_str if c.isdigit()])
    if digits:
        val = int(digits)
        formatted = f"{val:,}".replace(",", " ")
        return f"{formatted} so'm"
    
    return amount_str

def parse_receipt_text(text: str):
    """Xabarni qatorlar bo'yicha tahlil qilish."""
    if not text:
        return None, None, None

    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    if len(lines) < 3:
        return None, None, None

    invoice = clean_line(lines[0])
    client = clean_line(lines[1])
    raw_amount = clean_line(lines[2])

    amount = format_amount(raw_amount)

    return client, invoice, amount

def get_user_display_name(user) -> str:
    """Foydalanuvchining ismini yoki telegram usernameni chiroyli formatda qaytaradi."""
    if not user:
        return "Noma'lum"
    if user.username:
        return f"@{user.username}"
    first = user.first_name or ""
    last = user.last_name or ""
    name = f"{first} {last}".strip()
    return name if name else f"ID: {user.id}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot /start komandasi yuborilganda javob beradi."""
    user = update.effective_user
    logger.info(f"Start buyrug'i keldi. User ID: {user.id}")
    await update.message.reply_html(
        f"Salom {user.mention_html()}!\n\n"
        "Men kassa cheklarini tasdiqlovchi botman.\n"
        "Menga to'lov cheki (rasm yoki fayl) yuboring va ostiga ma'lumotlarni yozing. "
        "Men ularni tasdiqlash uchun umumiy guruhga yo'naltiraman.\n\n"
        "<b>Asosiy buyruqlar:</b>\n"
        "/my_id - O'zingizning shaxsiy Telegram ID raqamingizni bilish."
    )

async def get_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Foydalanuvchiga uning Telegram ID raqamini qaytaradi."""
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"Sizning Telegram ID raqamingiz: {chat_id}\n"
        f"Agar siz kassir bo'lsangiz, ushbu ID ni .env faylidagi CASHIER_IDS ro'yxatiga qo'shib qo'ying."
    )

async def send_format_warning(message, context: ContextTypes.DEFAULT_TYPE):
    """Noto'g'ri format haqida ogohlantirish yuborish."""
    logger.info(f"Foydalanuvchiga format xatosi haqida ogohlantirish yuborilmoqda: {message.from_user.id}")
    await message.reply_text(
        "⚠️ <b>To'lov ma'lumotlari formati noto'g'ri yoki to'liq emas!</b>\n\n"
        "Iltimos, rasmni tagiga (caption qismiga) ma'lumotlarni quyidagi tartibda yozib yuboring:\n"
        "<code>1-qator: Nakladnoy raqami\n"
        "2-qator: Mijoz nomi\n"
        "3-qator: Summa</code>\n\n"
        "<b>Masalan:</b>\n"
        "<code>99823\n"
        "Akfa OOO\n"
        "15000000</code>\n\n"
        "<i>(Summa probelsiz yoki 'so'm' so'zisiz yozilsa ham bot o'zi to'g'rilab oladi)</i>",
        parse_mode="HTML"
    )

async def proceed_with_receipt(main_message, all_messages, client, invoice, amount, context: ContextTypes.DEFAULT_TYPE):
    """To'lov ma'lumotlarini tekshirib guruhga yuborish."""
    logger.info(f"To'lovni qayta ishlash boshlandi. Nakladnoy: {invoice}, Mijoz: {client}, Summa: {amount}")
    
    # Dublikat tekshiruvi
    if db.check_invoice_exists(invoice):
        logger.info(f"Dublikat yuk hujjati aniqlandi: {invoice}")
        await main_message.reply_text(
            f"❌ <b>Yuk hujjati rad etildi!</b>\n"
            f"Diqqat, <code>{invoice}</code> raqamli yuk hujjati avval tasdiqlangan! "
            f"Qayta yuborish taqiqlanadi.",
            parse_mode="HTML"
        )
        return

    # Guruh sozlanmagan bo'lsa
    if not GROUP_CHAT_ID:
        logger.warning("GROUP_CHAT_ID sozlanmagan!")
        await main_message.reply_text("⚠️ Xatolik: Bot sozlamalarida to'lovlar guruhi sozlanmagan. Iltimos, administratorga xabar bering.")
        return

    # Bazaga yozish
    sender_display = get_user_display_name(main_message.from_user)
    sender_username = main_message.from_user.username or ""
    receipt_id = db.add_receipt(
        group_chat_id=GROUP_CHAT_ID,
        sender_id=main_message.from_user.id,
        sender_username=sender_username,
        sender_display_name=sender_display,
        client_name=client,
        invoice_number=invoice,
        amount=amount
    )

    # Guruhga yuboriladigan xabar matni (Yuboruvchi username bilan)
    sender_info = f"@{sender_username}" if sender_username else sender_display
    group_text = (
        f"📥 <b>Yangi to'lov cheki yuborildi!</b>\n\n"
        f"👤 <b>Yubordi:</b> {sender_display} ({sender_info})\n"
        f"🏢 <b>Mijoz:</b> {client}\n"
        f"📄 <b>Nakladnoy:</b> {invoice}\n"
        f"💰 <b>Summa:</b> {amount}\n"
    )

    # Kassir uchun guruhdagi tugmalar
    keyboard = [
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{receipt_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{receipt_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        # Agar bitta rasm/hujjat bo'lsa
        if len(all_messages) == 1:
            has_media = bool(main_message.photo or main_message.document)
            if has_media:
                logger.info(f"Bitta rasmli xabar guruhga ({GROUP_CHAT_ID}) nusxalanmoqda...")
                copied_msg = await context.bot.copy_message(
                    chat_id=GROUP_CHAT_ID,
                    from_chat_id=main_message.chat_id,
                    message_id=main_message.message_id,
                    caption=group_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
                group_message_id = copied_msg.message_id
            else:
                logger.info(f"Matnli xabar guruhga ({GROUP_CHAT_ID}) yuborilmoqda...")
                sent_msg = await context.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=group_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
                group_message_id = sent_msg.message_id
        
        # Agar ko'p rasm (albom) bo'lsa
        else:
            logger.info(f"Albom ko'rinishidagi {len(all_messages)} ta rasm guruhga ({GROUP_CHAT_ID}) yuborilmoqda...")
            media_list = []
            for msg in all_messages:
                if msg.photo:
                    file_id = msg.photo[-1].file_id
                    media_list.append(InputMediaPhoto(media=file_id))
                elif msg.document:
                    file_id = msg.document.file_id
                    media_list.append(InputMediaDocument(media=file_id))
            
            # Albomni guruhga yuborish
            sent_media_msgs = await context.bot.send_media_group(
                chat_id=GROUP_CHAT_ID,
                media=media_list
            )
            first_media_msg_id = sent_media_msgs[0].message_id

            # Albom ostidan tugmalar va tafsilotlarni yuborish (reply qilib)
            sent_details_msg = await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=group_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                reply_to_message_id=first_media_msg_id
            )
            group_message_id = sent_details_msg.message_id

        # Bazaga guruh xabari ID sini yozib qo'yish
        db.update_group_message_id(receipt_id, group_message_id)
        logger.info(f"To'lov guruhga yuborildi. Guruh xabar ID: {group_message_id}")

        # Agentga shaxsiy chatida tasdiqlashga yuborilganini bildirish
        await main_message.reply_text("⏳ To'lov guruhga tasdiqlash uchun yuborildi. Kassir ko'rib chiqqanidan so'ng sizga hisobot boradi.")

    except Exception as e:
        logger.error(f"Guruhga xabar yuborishda xatolik: {e}", exc_info=True)
        await main_message.reply_text("⚠️ Xatolik: To'lovni guruhga yo'naltirib bo'lmadi. Bot sozlamalarini tekshiring.")

async def process_media_group(media_id: str, context: ContextTypes.DEFAULT_TYPE):
    """Albomdagi barcha rasmlar kelib bo'lgach ishlaydigan funksiya."""
    await asyncio.sleep(1.2)
    
    messages = MEDIA_GROUPS.pop(media_id, [])
    if not messages:
        return

    logger.info(f"Albom qabul qilindi. Rasmlar soni: {len(messages)}, media_group_id: {media_id}")
    main_message = None
    client, invoice, amount = None, None, None

    for msg in messages:
        text_content = msg.caption if msg.caption else msg.text
        cl, inv, am = parse_receipt_text(text_content)
        if cl and inv and am:
            main_message = msg
            client, invoice, amount = cl, inv, am
            break

    if not main_message:
        logger.info("Albom ichidan to'g'ri formatdagi matn topilmadi.")
        first_msg = messages[0]
        await send_format_warning(first_msg, context)
        return

    await proceed_with_receipt(main_message, messages, client, invoice, amount, context)

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Agentlarning shaxsiy chatidan kelgan cheklarni qabul qiladi."""
    message = update.message
    if not message:
        return

    if message.from_user and message.from_user.is_bot:
        return

    # Batafsil log yozish (Kelgan xabarni kuzatish uchun)
    logger.info(
        f"YANGI XABAR KELDI -> Chat ID: {message.chat_id}, Chat turi: {message.chat.type}, "
        f"Yuboruvchi: {message.from_user.id} ({message.from_user.username}), "
        f"Media Group: {message.media_group_id}, Caption: {bool(message.caption)}, Text: {bool(message.text)}"
    )

    # Faqat shaxsiy chatda ishlashi kerak (guruhlardagi oddiy yozishmalarga aralashmaslik uchun)
    if message.chat.type != "private":
        logger.info(f"Xabar shaxsiy chatdan kelmagani uchun bekor qilindi (Chat turi: {message.chat.type})")
        return

    has_media = bool(message.photo or message.document)
    is_text = bool(message.text)

    if not (has_media or is_text):
        logger.info("Xabar rasm, fayl yoki matn emasligi uchun bekor qilindi.")
        return

    # Albom (media group) bo'lsa
    if message.media_group_id:
        media_id = message.media_group_id
        if media_id not in MEDIA_GROUPS:
            MEDIA_GROUPS[media_id] = [message]
            asyncio.create_task(process_media_group(media_id, context))
        else:
            MEDIA_GROUPS[media_id].append(message)
    else:
        text_content = message.caption if message.caption else message.text
        client, invoice, amount = parse_receipt_text(text_content)

        if not client or not invoice or not amount:
            logger.info(f"Matn formati xato: '{text_content}'")
            await send_format_warning(message, context)
            return

        await proceed_with_receipt(message, [message], client, invoice, amount, context)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Guruhda kassir tasdiqlash/rad etish tugmasini bosganida ishlaydi."""
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    logger.info(f"Tugma bosildi. Callback: {callback_data}, Bosgan user: {query.from_user.id}")
    
    if not (callback_data.startswith("approve_") or callback_data.startswith("reject_")):
        return

    action, receipt_id_str = callback_data.split("_")
    receipt_id = int(receipt_id_str)

    group_message_id = query.message.message_id
    receipt = db.get_receipt_by_group_message(group_message_id)

    if not receipt:
        await query.answer("Xato: To'lov ma'lumotlari bazadan topilmadi.", show_alert=True)
        return

    # Status kutilayotgan holatda ekanligini tekshirish
    if receipt['status'] != 'pending':
        await query.answer(f"Bu to'lov allaqachon ko'rib chiqilgan! (Holati: {receipt['status']})", show_alert=True)
        await query.edit_message_reply_markup(reply_markup=None)
        return

    # Ruxsatni tekshirish (Faqat CASHIER_IDS ro'yxatidagi kassirlar tasdiqlay oladi)
    user_id = query.from_user.id
    if user_id not in CASHIER_IDS:
        await query.answer("Sizda to'lovni tasdiqlash uchun huquq yo'q! 🛑", show_alert=True)
        return

    cashier_name = get_user_display_name(query.from_user)
    current_time = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

    # Bazani yangilash
    db.update_receipt_status(receipt_id, action)

    # 1. Guruhdagi xabar matnini yangilash va tugmalarni olib tashlash
    status_label = "✅ Tasdiqlandi" if action == "approve" else "❌ Rad etildi"
    
    sender_info = f"@{receipt['sender_username']}" if receipt['sender_username'] else receipt['sender_display_name']
    updated_group_text = (
        f"📥 <b>To'lov cheki qayta ishlandi</b>\n\n"
        f"👤 <b>Yubordi:</b> {receipt['sender_display_name']} ({sender_info})\n"
        f"🏢 <b>Mijoz:</b> {receipt['client_name']}\n"
        f"📄 <b>Nakladnoy:</b> {receipt['invoice_number']}\n"
        f"💰 <b>Summa:</b> {receipt['amount']}\n\n"
        f"<b>Holat:</b> {status_label}\n"
        f"👤 <b>Kassir:</b> {cashier_name}\n"
        f"🕒 <b>Vaqt:</b> {current_time}"
    )

    if query.message.caption:
        await query.edit_message_caption(caption=updated_group_text, parse_mode="HTML", reply_markup=None)
    else:
        await query.edit_message_text(text=updated_group_text, parse_mode="HTML", reply_markup=None)

    # 2. Agentning o'ziga shaxsiy chatida javob (feedback) yuborish
    agent_chat_id = receipt['sender_id']
    
    if action == "approve":
        agent_feedback = (
            f"✅ <b>Siz yuborgan to'lov tasdiqlandi!</b>\n\n"
            f"📄 <b>Nakladnoy raqami:</b> {receipt['invoice_number']}\n"
            f"💰 <b>Tasdiqlangan summa:</b> {receipt['amount']}\n"
            f"👤 <b>Tasdiqlagan kassir:</b> {cashier_name}"
        )
    else:
        agent_feedback = (
            f"❌ <b>Siz yuborgan to'lov rad etildi!</b>\n\n"
            f"📄 <b>Nakladnoy raqami:</b> {receipt['invoice_number']}\n"
            f"💰 <b>Summa:</b> {receipt['amount']}\n"
            f"👤 <b>Rad etgan kassir:</b> {cashier_name}\n\n"
            f"<i>Iltimos, ma'lumotlarni qayta tekshirib, chekni boshqatdan yuboring.</i>"
        )

    try:
        await context.bot.send_message(
            chat_id=agent_chat_id,
            text=agent_feedback,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Agentga shaxsiy xabar yuborishda xatolik: {e}")

def main() -> None:
    """Botni ishga tushirish."""
    if not TOKEN or TOKEN == "your_bot_token_here":
        print("XATOLIK: TELEGRAM_BOT_TOKEN sozlanmagan! .env faylini tekshiring.")
        return

    # Render.com port band qilishi uchun veb-serverni alohida thread'da boshlash
    threading.Thread(target=run_health_check_server, daemon=True).start()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("my_id", get_my_id))

    # Agentning shaxsiy xabarlarini ushlash (filters.ALL ishlatilib handler ichida filtrlash)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_receipt))

    # Guruhdagi tugmalar bosilishini ushlash
    application.add_handler(CallbackQueryHandler(button_callback))

    print("Bot muvaffaqiyatli ishga tushdi (Inverted workflow)...")
    application.run_polling()

if __name__ == "__main__":
    main()
