"""Telegram bot handlers - single-owner personal assistant.

Only TELEGRAM_OWNER_ID may talk to the bot; everyone else is silently
ignored (no auth prompt - this isn't a public bot).
"""
from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.bot import agent
from app.config import settings
from app.tools import portfolio

logger = logging.getLogger(__name__)


def _is_owner(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == settings.telegram_owner_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    await update.message.reply_text(
        "Xin chào! Tôi là trợ lý theo dõi chứng khoán cá nhân của bạn.\n"
        "Hỏi tôi về giá cổ phiếu, danh mục, hoặc watchlist. "
        "Lệnh: /portfolio /watchlist"
    )


async def _ask_and_reply(update: Update, prompt_text: str) -> None:
    """Call the agent and reply, surfacing a friendly message on failure
    instead of leaving the user with no response (e.g. Claude auth not set
    up yet, VNDirect blocked, Supabase unreachable)."""
    try:
        reply = await asyncio.to_thread(agent.ask, update.effective_chat.id, prompt_text)
    except Exception:
        logger.exception("agent.ask failed")
        await update.message.reply_text(
            "Có lỗi khi xử lý yêu cầu (có thể do chưa cấu hình xong Claude/dữ liệu "
            "giá). Kiểm tra log server để biết chi tiết."
        )
        return
    await update.message.reply_text(reply)


async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    await _ask_and_reply(update, "Cho tôi xem danh mục hiện tại.")


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    await _ask_and_reply(update, "Cho tôi xem watchlist hiện tại.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    await _ask_and_reply(update, update.message.text)


async def check_alerts(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        messages = await asyncio.to_thread(portfolio.check_watchlist_alerts)
    except Exception:
        logger.exception("Alert check failed")
        return
    for msg in messages:
        await context.bot.send_message(chat_id=settings.telegram_owner_id, text=msg)


def build_application() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("portfolio", portfolio_command))
    app.add_handler(CommandHandler("watchlist", watchlist_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.job_queue.run_repeating(check_alerts, interval=300, first=60)
    return app
