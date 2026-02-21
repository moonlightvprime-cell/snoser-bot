import os
import re
import asyncio
import random
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.ext._updater import Updater

# ============================================
# ТВОИ ДАННЫЕ
# ============================================
BOT_TOKEN = "8017274514:AAHWUrr5DkJgSytkSLfXlA_zs_5B9c5fAQU"
ALLOWED_USERS = [7537795172, 5131389305]
SITE_URL = "https://sites.google.com/view/probyv-site-"

# ============================================
# АККАУНТЫ ДЛЯ СНОСЕРА
# ============================================
SENDER_ACCOUNTS = [
    {'email': 'testbotyra@gmail.com', 'password': 'ahgixwqkvlthbeoc'},
    {'email': 'zxcboomxd@gmail.com', 'password': 'whxdghbznuyghfpj'}
]

COMPLAINT_TEXTS = [
    """Здравствуйте уважаемая поддержка телеграм, сегодня у меня украли мой аккаунт @{target} и я не могу сбросить пароль потому что его отменяют, уберите пожалуйста злоумышленников с моего аккаунта""",
    """Срочно! Мой аккаунт @{target} взломан! Мошенники рассылают спам от моего имени. Прошу заблокировать аккаунт.""",
    """Внимание поддержка! Аккаунт @{target} скомпрометирован. Злоумышленники получили к нему доступ. Требуется срочная блокировка!"""
]

TARGET_EMAIL = 'recover@telegram.org'

# Очередь задач
task_queue = asyncio.Queue()
user_sessions = {}

# ============================================
# FLASK ПРИЛОЖЕНИЕ (ДЛЯ ВЕБХУКА)
# ============================================
flask_app = Flask(__name__)

# Создаем приложение бота
bot_app = Application.builder().token(BOT_TOKEN).build()


# ============================================
# ГЛАВНОЕ МЕНЮ
# ============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Нет доступа")
        return

    keyboard = [
        [InlineKeyboardButton("💥 СНОСЕР", callback_data="menu_snos")],
        [InlineKeyboardButton("🌐 ОТКРЫТЬ САЙТ", url=SITE_URL)]
    ]

    await update.message.reply_text(
        "👋 **ГЛАВНОЕ МЕНЮ**\n\n"
        "💥 **СНОСЕР** - массовые жалобы на аккаунты\n"
        "🌐 **САЙТ** - открыть сайт с информацией\n\n"
        f"🔗 {SITE_URL}",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================
# ОБРАБОТКА МЕНЮ
# ============================================
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data == "menu_snos":
        user_sessions[user_id] = {'mode': 'snoser', 'step': 'waiting_username'}
        await query.edit_message_text(
            "💥 **СНОСЕР**\n\nВведи username цели:",
            parse_mode='Markdown'
        )


# ============================================
# СНОСЕР - ВВОД USERNAME
# ============================================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in user_sessions:
        await update.message.reply_text("Сначала нажми /start")
        return

    mode = user_sessions[user_id].get('mode')
    step = user_sessions[user_id].get('step')

    if mode == 'snoser' and step == 'waiting_username':
        target = text.replace('@', '').strip()
        user_sessions[user_id]['target'] = target
        user_sessions[user_id]['step'] = 'waiting_count'

        keyboard = [
            [InlineKeyboardButton("🔹 10", callback_data="sn_10"),
             InlineKeyboardButton("🔸 25", callback_data="sn_25")],
            [InlineKeyboardButton("⚡ 50", callback_data="sn_50"),
             InlineKeyboardButton("💥 100", callback_data="sn_100")]
        ]

        await update.message.reply_text(
            f"✅ **Цель:** @{target}\n\nВыбери количество жалоб:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# ============================================
# СНОСЕР - ВЫБОР КОЛИЧЕСТВА
# ============================================
async def snoser_count_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    count = int(query.data.split('_')[1])

    if user_id in user_sessions and 'target' in user_sessions[user_id]:
        target = user_sessions[user_id]['target']

        # Добавляем задачу в очередь
        await task_queue.put({
            'user_id': user_id,
            'target': target,
            'count': count,
            'bot': context.bot
        })

        await query.edit_message_text(
            f"📦 **Задача добавлена в очередь!**\n\n"
            f"👤 Цель: @{target}\n"
            f"📊 Количество: {count}\n\n"
            f"Я начну отправку и пришлю результат.\n"
            f"Ты можешь продолжать пользоваться ботом."
        )

        del user_sessions[user_id]

        # Возвращаем меню
        keyboard = [
            [InlineKeyboardButton("💥 СНОСЕР", callback_data="menu_snos")],
            [InlineKeyboardButton("🌐 ОТКРЫТЬ САЙТ", url=SITE_URL)]
        ]

        await query.message.reply_text(
            "👋 **ГЛАВНОЕ МЕНЮ**",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# ============================================
# СНОСЕР - ФУНКЦИЯ ОТПРАВКИ
# ============================================
async def snoser_send(target, count):
    print("\n" + "=" * 70)
    print(f"🚀 ЗАПУСК СНОСА НА @{target}")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print(f"{'№':<5} {'Отправитель':<25} {'Статус':<10} {'Время':<20}")
    print("-" * 70)

    sent = 0
    errors = 0

    for i in range(count):
        current = i + 1
        sender = random.choice(SENDER_ACCOUNTS)
        text = random.choice(COMPLAINT_TEXTS).format(target=target)

        try:
            msg = MIMEMultipart()
            msg["From"] = sender['email']
            msg["To"] = TARGET_EMAIL
            msg["Subject"] = f"СРОЧНО! Аккаунт @{target} взломан!"
            msg.attach(MIMEText(text, "plain", "utf-8"))

            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(sender['email'], sender['password'])
            server.send_message(msg)
            server.quit()

            sent += 1
            status = "✅ УСПЕХ"
            print(f"{current:<5} {sender['email']:<25} {status:<10} {datetime.now().strftime('%H:%M:%S'):<20}")

            if current < count:
                delay = random.uniform(2, 4)
                await asyncio.sleep(delay)

        except Exception as e:
            errors += 1
            status = "❌ ОШИБКА"
            error_short = str(e)[:30]
            print(f"{current:<5} {sender['email']:<25} {status:<10} {error_short}")

    print("=" * 70)
    print(f"🏁 ЗАВЕРШЕНО! Успешно: {sent}, Ошибок: {errors}")
    print("=" * 70 + "\n")

    return f"✅ Успешно: {sent}\n❌ Ошибок: {errors}"


# ============================================
# ОБРАБОТЧИК ОЧЕРЕДИ
# ============================================
async def queue_worker():
    while True:
        try:
            task = await task_queue.get()

            await task['bot'].send_message(
                chat_id=task['user_id'],
                text=f"🔄 **Начинаю отправку {task['count']} жалоб на @{task['target']}**"
            )

            result = await snoser_send(task['target'], task['count'])

            await task['bot'].send_message(
                chat_id=task['user_id'],
                text=f"✅ **ГОТОВО!**\n\n{result}"
            )

        except Exception as e:
            print(f"❌ Ошибка в очереди: {e}")


# ============================================
# ДОБАВЛЯЕМ ОБРАБОТЧИКИ В БОТА
# ============================================
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu_"))
bot_app.add_handler(CallbackQueryHandler(snoser_count_handler, pattern="^sn_"))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))


# ============================================
# FLASK МАРШРУТЫ
# ============================================
@flask_app.route('/')
def index():
    return 'Бот работает!', 200


@flask_app.route('/health')
def health():
    return 'OK', 200


@flask_app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Принимаем обновления от Telegram"""
    try:
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        asyncio.run_coroutine_threadsafe(bot_app.process_update(update), bot_app.loop)
        return 'OK', 200
    except Exception as e:
        print(f"Ошибка в вебхуке: {e}")
        return 'Error', 500


# ============================================
# ЗАПУСК
# ============================================
async def run_bot():
    """Запускаем бота и очередь задач"""
    # Запускаем очередь
    asyncio.create_task(queue_worker())
    print("✅ Очередь задач запущена")

    # Запускаем бота
    await bot_app.initialize()
    await bot_app.start()

    # Устанавливаем вебхук
    host = os.environ.get('RENDER_EXTERNAL_URL', 'https://localhost:5000')
    webhook_url = f"{host}/{BOT_TOKEN}"
    await bot_app.bot.set_webhook(webhook_url)
    print(f"✅ Вебхук установлен на {webhook_url}")

    # Держим бота живым
    while True:
        await asyncio.sleep(60)


def main():
    """Точка входа для TeleBotHost"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Запускаем бота в отдельной задаче
    loop.create_task(run_bot())

    # Запускаем Flask (блокирующий вызов)
    flask_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))


if __name__ == '__main__':
    print("\n" + "🔥" * 70)
    print("🔥 БОТ ЗАПУЩЕН (ВЕБХУК + СНОСЕР)")
    print("🔥" * 70 + "\n")
    print(f"🤖 Токен: {BOT_TOKEN[:10]}...")
    print(f"👤 Админы: {ALLOWED_USERS}")
    print(f"🌐 Сайт: {SITE_URL}")
    print("\n✅ Режимы:")
    print("   💥 СНОСЕР - жалобы на аккаунты")
    print("   🌐 САЙТ - открыть сайт")
    print("\n🚀 Бот работает через вебхук!")
    print("🔥" * 70 + "\n")

    main()
