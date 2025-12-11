import os
import logging
import re
from typing import Dict, List, Optional

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# Загрузка .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS", "")
ADMIN_IDS_LIST = [int(x.strip()) for x in ADMIN_IDS.split(",") if x.strip()]

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в окружении")

# Простое in-memory хранилище (user_id -> open True/False)
open_chats: Dict[int, bool] = {}

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS_LIST

def format_user_label(user_id: int, user) -> str:
    name = user.full_name if user else "Unknown"
    username = f"@{user.username}" if getattr(user, "username", None) else ""
    return f"From: {name} {username}\nID: {user_id}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Это бот поддержки. Отправь сообщение — администратор получит его."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - приветствие\n/myid - показать ваш Telegram ID\n/help - помощь\n\nАдминистратору: /reply <user_id> <текст> или ответ (reply) на служебное сообщение"
    )

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(f"Ваш Telegram ID: {uid}")

# Когда пользователь присылает любое сообщение
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = update.effective_user
    user_id = user.id

    # Отметим чат как открытый
    open_chats[user_id] = True

    # Копируем сообщение администраторам (copy_message лучше для сохранения типа медиа)
    for admin_id in ADMIN_IDS_LIST:
        try:
            # Копируем содержимое
            await context.bot.copy_message(chat_id=admin_id, from_chat_id=msg.chat_id, message_id=msg.message_id)
            # Отправляем метку с ID и именем — чтобы админ мог нажать reply на неё
            label = format_user_label(user_id, user)
            sent = await context.bot.send_message(chat_id=admin_id, text=label)
            # (опционально) можно сохранять связь между message_id админа и user_id, если нужно
        except Exception as e:
            logger.exception("Не удалось переслать сообщение админам: %s", e)

    # Подтверждение пользователю
    await msg.reply_text("Сообщение отправлено администратору. Ожидайте ответа.")

# Команда /reply для админа: /reply <user_id> <текст>
async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user
    if not is_admin(sender.id):
        await update.message.reply_text("Только администратор может использовать эту команду.")
        return

    args = context.args
    if not args or len(args) < 2:
        # Также поддерживаем вариант: админ отвечает reply_to message (в этом случае парсим user_id из replied message)
        if update.message.reply_to_message:
            # Попробуем извлечь user_id из replied message текста "ID: <user_id>"
            text = update.message.reply_to_message.text or ""
            m = re.search(r"ID:\s*(\d+)", text)
            if m:
                user_id = int(m.group(1))
                # Текст ответа — берем весь текст после команды (если есть)
                reply_text = " ".join(args) if args else ""
                if not reply_text:
                    await update.message.reply_text("Укажите текст ответа после команды или напишите: /reply <user_id> <текст>")
                    return
            else:
                await update.message.reply_text("Не удалось найти ID пользователя в reply_to. Используйте /reply <user_id> <текст>")
                return
        else:
            await update.message.reply_text("Использование: /reply <user_id> <текст>")
            return
    else:
        try:
            user_id = int(args[0])
        except ValueError:
            await update.message.reply_text("Неверный user_id. Должно быть число.")
            return
        reply_text = " ".join(args[1:])

    # Шлём пользователю текст
    try:
        await context.bot.send_message(chat_id=user_id, text=f"Ответ от админа:\n{reply_text}")
        await update.message.reply_text("Сообщение отправлено пользователю.")
    except Exception as e:
        logger.exception("Ошибка при отправке сообщения пользователю: %s", e)
        await update.message.reply_text(f"Не удалось отправить сообщение: {e}")

# Команда /close <user_id> — админ закрывает чат
async def close_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user
    if not is_admin(sender.id):
        await update.message.reply_text("Только администратор может закрывать чат.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /close <user_id>")
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный user_id.")
        return

    open_chats.pop(user_id, None)
    try:
        await context.bot.send_message(chat_id=user_id, text="Чат с администратором закрыт. Спасибо!")
    except Exception:
        pass
    await update.message.reply_text(f"Чат с {user_id} закрыт.")

# Ловим любые сообщения от админов, когда они отвечают reply_to служебного сообщения
async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user
    if not is_admin(sender.id):
        return  # игнорируем обычных пользователей в этом хендлере

    # Если админ отвечает на служебное сообщение (reply_to)
    if update.message.reply_to_message:
        text = update.message.reply_to_message.text or ""
        m = re.search(r"ID:\s*(\d+)", text)
        if m:
            user_id = int(m.group(1))
            # отправляем содержимое ответа пользователю (только текст)
            try:
                # если админ прислал медиа/фото/стикер — можно расширить логику
                if update.message.text:
                    await context.bot.send_message(chat_id=user_id, text=f"Ответ от администратора:\n{update.message.text}")
                else:
                    await update.message.reply_text("В данный момент поддерживаются только текстовые ответы через этот путь. Используйте /reply для отправки медиа.")
                await update.message.reply_text("Отправлено пользователю.")
            except Exception as e:
                logger.exception("Ошибка отправки ответа пользователю: %s", e)
                await update.message.reply_text(f"Не удалось отправить: {e}")
            return

    # Если админ просто пишет в личку боту — подсказка
    await update.message.reply_text("Чтобы ответить пользователю: используйте /reply <user_id> <текст> или ответьте на служебное сообщение (reply).")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("reply", reply_cmd))
    app.add_handler(CommandHandler("close", close_cmd))

    # Обработчики сообщений:
    # - Сообщения от админов (личка боту) обрабатываем отдельно
    app.add_handler(MessageHandler(filters.ALL & filters.USER(user_id=ADMIN_IDS_LIST), handle_admin_message))

    # - Сообщения от всех остальных — пересылаем админам
    app.add_handler(MessageHandler(filters.ALL & ~filters.User(user_id=ADMIN_IDS_LIST), handle_user_message))

    # Запуск polling
    app.run_polling()

if __name__ == "__main__":
    main()
