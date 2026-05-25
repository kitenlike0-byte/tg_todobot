import os
import sqlite3
from datetime import datetime, timedelta
import random
import threading
import time
import http.server
import threading

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)

from apscheduler.schedulers.background import BackgroundScheduler

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not found")

# ================= DB =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    text TEXT,
    priority INTEGER,
    status TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    text TEXT,
    time TEXT
)
""")

conn.commit()

# ================= HELPERS =================
def add_task(user_id, text, priority=1):
    cursor.execute(
        "INSERT INTO tasks VALUES (NULL,?,?,?,?,?)",
        (user_id, text, priority, "pending", datetime.now().isoformat())
    )
    conn.commit()

def get_tasks(user_id):
    cursor.execute(
        "SELECT id, text, priority FROM tasks WHERE user_id=? AND status='pending'",
        (user_id,)
    )
    return cursor.fetchall()

def set_done(task_id, user_id):
    cursor.execute(
        "UPDATE tasks SET status='done' WHERE id=? AND user_id=?",
        (task_id, user_id)
    )
    conn.commit()

def add_reminder(user_id, text, time_str):
    cursor.execute(
        "INSERT INTO reminders VALUES (NULL,?,?,?)",
        (user_id, text, time_str)
    )
    conn.commit()

# ================= AI PLANNER (упрощённый) =================
def ai_plan(tasks):
    """
    имитация AI:
    - важные выше
    - случайно распределяем время блоками
    """
    sorted_tasks = sorted(tasks, key=lambda x: x[2], reverse=True)

    schedule = []
    start_hour = 9

    for t in sorted_tasks:
        duration = random.choice([15, 30, 45, 60])

        schedule.append({
            "task": t[1],
            "time": f"{start_hour}:00",
            "duration": duration
        })

        start_hour += duration // 30

    return schedule

# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 V4 AI Planner\n\n"
        "/dump\n/add\n/today\n/remind\n/focus"
    )

# ---------- DUMP ----------
async def dump(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    items = [x.strip() for x in text.split(",")]

    for i, item in enumerate(items):
        priority = 3 if i == 0 else 2 if i == 1 else 1
        add_task(update.effective_user.id, item, priority)

    await update.message.reply_text("🧠 задачи разобраны")

# ---------- TODAY (AI PLAN) ----------
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = get_tasks(update.effective_user.id)

    if not tasks:
        return await update.message.reply_text("пусто")

    plan = ai_plan(tasks)

    msg = "📅 ТВОЙ ДЕНЬ (AI PLAN)\n\n"

    for p in plan:
        msg += f"{p['time']} → {p['task']} ({p['duration']}м)\n"

    msg += "\n🧠 режим: auto-структура дня"

    await update.message.reply_text(msg)

# ---------- ADD ----------
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)

    if not text:
        return await update.message.reply_text(
            "Использование:\n/add купить хлеб"
        )

    add_task(update.effective_user.id, text, 2)

    await update.message.reply_text("✅ Добавлено")

# ---------- REMINDER ----------
async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        return await update.message.reply_text(
            "Использование:\n/remind 18:00 спорт"
        )

    time_str = context.args[0]
    text = " ".join(context.args[1:])

    add_reminder(update.effective_user.id, text, time_str)

    await update.message.reply_text(
        f"⏰ Напоминание поставлено на {time_str}"
    )

# ---------- FOCUS ----------
async def focus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    minutes = int(context.args[0])

    await update.message.reply_text(
        f"🎯 focus {minutes} мин\nубери отвлечения"
    )

# ================= SCHEDULER =================
scheduler = BackgroundScheduler()

def check_reminders():
    now = datetime.now().strftime("%H:%M")

    cursor.execute(
        "SELECT id, user_id, text FROM reminders WHERE time=?",
        (now,)
    )

    rows = cursor.fetchall()

    for r in rows:
        print(f"REMINDER: {r}")
scheduler.add_job(check_reminders, "interval", seconds=30)

def run_scheduler():
    scheduler.start()
    while True:
        time.sleep(10)

threading.Thread(target=run_scheduler, daemon=True).start()

# ================= MAIN =================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dump", dump))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("focus", focus))

    print("V4 running...")
    app.run_polling()

if __name__ == "__main__":
    main()

# Простейший хэндлер, который на любой запрос ответит "ОК"
class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_check():
    # Render автоматически передает нужный порт в переменную окружения PORT
    port = int(os.getenv("PORT", 10000))
    server = http.server.HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"Fake web-server started on port {port}")
    server.serve_forever()

# ================= MAIN =================
def main():
    # 1. Запускаем фейковый веб-сервер в отдельном потоке для Render
    threading.Thread(target=run_health_check, daemon=True).start()

    # 2. Инициализируем и запускаем бота
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dump", dump))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("focus", focus))

    print("V4 running...")
    app.run_polling()

if name == "__main__":
    main()
