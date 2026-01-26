import os
import sqlite3
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
BOT_TOKEN = "8315956970:AAGFq1nVflHIOu1v9_6pHNN61LQBuHf4xN0"

# ---------- DATABASE ----------
conn = sqlite3.connect("vip_emails.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS vip (email TEXT PRIMARY KEY)")
conn.commit()

# ---------- GMAIL AUTH ----------
def gmail_auth():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

service = gmail_auth()

# ---------- COMMANDS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Mail Alert Bot Active!\n\n"
        "Commands:\n"
        "/addvip email\n"
        "/removevip email\n"
        "/viplist\n"
        "/checkmail"
    )

async def addvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /addvip email")
        return
    email = context.args[0]
    cur.execute("INSERT OR IGNORE INTO vip VALUES(?)", (email,))
    conn.commit()
    await update.message.reply_text(f"✅ Added VIP: {email}")

async def removevip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /removevip email")
        return
    email = context.args[0]
    cur.execute("DELETE FROM vip WHERE email=?", (email,))
    conn.commit()
    await update.message.reply_text(f"❌ Removed VIP: {email}")

async def viplist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur.execute("SELECT email FROM vip")
    rows = cur.fetchall()
    if not rows:
        await update.message.reply_text("No VIP emails added.")
        return
    text = "⭐ VIP Emails:\n\n"
    for r in rows:
        text += f"- {r[0]}\n"
    await update.message.reply_text(text)

# ---------- FETCH MAIL ----------
def fetch_vip_mails():
    cur.execute("SELECT email FROM vip")
    vip_list = [r[0] for r in cur.fetchall()]
    if not vip_list:
        return []

    query = " OR ".join([f"from:{e}" for e in vip_list])
    results = service.users().messages().list(
        userId='me', q=query, maxResults=5
    ).execute()
    return results.get('messages', [])

async def checkmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mails = fetch_vip_mails()
    if not mails:
        await update.message.reply_text("📭 No new VIP mails.")
        return

    text = "🔔 Important Mails:\n\n"
    for msg in mails:
        m = service.users().messages().get(userId='me', id=msg['id']).execute()
        headers = m['payload']['headers']
        subject = sender = ""
        for h in headers:
            if h['name'] == 'Subject':
                subject = h['value']
            if h['name'] == 'From':
                sender = h['value']
        text += f"From: {sender}\nSubject: {subject}\n\n"

    await update.message.reply_text(text)

# ---------- AUTO CHECK ----------
last_ids = set()

async def auto_check(context: ContextTypes.DEFAULT_TYPE):
    global last_ids
    mails = fetch_vip_mails()
    for msg in mails:
        if msg['id'] not in last_ids:
            last_ids.add(msg['id'])
            m = service.users().messages().get(userId='me', id=msg['id']).execute()
            headers = m['payload']['headers']
            subject = sender = ""
            for h in headers:
                if h['name'] == 'Subject':
                    subject = h['value']
                if h['name'] == 'From':
                    sender = h['value']
            await context.bot.send_message(
                chat_id=context.job.chat_id,
                text=f"🔔 New Important Mail!\n\nFrom: {sender}\nSubject: {subject}"
            )

# ---------- MAIN ----------
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addvip", addvip))
app.add_handler(CommandHandler("removevip", removevip))
app.add_handler(CommandHandler("viplist", viplist))
app.add_handler(CommandHandler("checkmail", checkmail))

job_queue = app.job_queue
job_queue.run_repeating(auto_check, interval=300, first=10)

print("🤖 Bot Running...")
app.run_polling()
