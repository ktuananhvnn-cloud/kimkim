"""Entrypoint: runs the Telegram bot (polling) and the admin FastAPI site
in one process/container - simplest deployment shape for a solo project.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.admin.main import router as admin_router
from app.bot.handlers import build_application
from app.config import settings

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    telegram_app = build_application()
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    logger.info("Telegram bot polling started")
    try:
        yield
    finally:
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
        logger.info("Telegram bot stopped")


app = FastAPI(title="Stock Agent", lifespan=lifespan)
app.include_router(admin_router)


@app.get("/")
def root():
    return RedirectResponse(url="/admin")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


def main():
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.admin_port,
        log_level=settings.log_level.lower(),
        # The container only listens on 127.0.0.1, reachable solely via the
        # trusted local reverse proxy (see README) - trust its X-Forwarded-*
        # headers so request.url.scheme correctly reports "https" in prod,
        # which is what makes the admin session cookie's Secure flag work.
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
