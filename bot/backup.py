"""
بکاپ و بازیابی دیتابیس PostgreSQL — دامپ خودکار/دستی و restore از فایل.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile
from asgiref.sync import sync_to_async

from bot.constants import CREATOR_USER_ID

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(tempfile.gettempdir()) / "tasino_backups"
BACKUP_KEEP = 8  # حداکثر فایل محلی نگه‌داری‌شده
DUMP_SUFFIX = ".dump"

# مسیر فایل در انتظار تأیید بازیابی: user_id → Path
PENDING_RESTORE: dict[int, Path] = {}


def _db_params() -> dict:
    from django.conf import settings
    db = settings.DATABASES["default"]
    return {
        "name": db.get("NAME") or "tasino_db",
        "user": db.get("USER") or "postgres",
        "password": db.get("PASSWORD") or "",
        "host": db.get("HOST") or "localhost",
        "port": str(db.get("PORT") or "5432"),
    }


def _pg_env() -> dict:
    env = os.environ.copy()
    env["PGPASSWORD"] = str(_db_params()["password"])
    # جلوگیری از پرسش interactive
    env["PGOPTIONS"] = "-c client_min_messages=warning"
    return env


def _ensure_dir() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def _cleanup_old_files() -> None:
    try:
        files = sorted(
            BACKUP_DIR.glob(f"tasino_backup_*{DUMP_SUFFIX}"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in files[BACKUP_KEEP:]:
            try:
                old.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception as e:
        logger.debug("cleanup backups: %s", e)


def _which_pg(tool: str) -> str | None:
    return shutil.which(tool)


def create_dump_sync() -> tuple[Path | None, str]:
    """
    ساخت دامپ با pg_dump (فرمت custom فشرده).
    خروجی: (path, error_or_ok_message)
    """
    if not _which_pg("pg_dump"):
        return None, (
            "❌ ابزار <code>pg_dump</code> روی سرور نصب نیست.\n"
            "در Docker پکیج <code>postgresql-client</code> لازم است."
        )

    params = _db_params()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = _ensure_dir() / f"tasino_backup_{stamp}{DUMP_SUFFIX}"

    cmd = [
        "pg_dump",
        "-h", params["host"],
        "-p", params["port"],
        "-U", params["user"],
        "-d", params["name"],
        "-Fc",
        "--no-owner",
        "--no-acl",
        "-f", str(out),
    ]
    try:
        proc = __import__("subprocess").run(
            cmd,
            env=_pg_env(),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except Exception as e:
        return None, f"❌ اجرای pg_dump شکست خورد: {e}"

    if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        err = (proc.stderr or proc.stdout or "unknown").strip()[:500]
        try:
            out.unlink(missing_ok=True)
        except Exception:
            pass
        return None, f"❌ pg_dump خطا داد:\n<code>{err}</code>"

    _cleanup_old_files()
    size_mb = out.stat().st_size / (1024 * 1024)
    return out, f"✅ دامپ آماده — {size_mb:.2f} MB"


def restore_dump_sync(path: Path) -> tuple[bool, str]:
    """بازیابی از فایل .dump (custom) یا .sql / .sql.gz."""
    path = Path(path)
    if not path.exists():
        return False, "❌ فایل دامپ پیدا نشد."

    # قطع اتصال‌های Django قبل از restore
    try:
        from django.db import connections
        connections.close_all()
    except Exception:
        pass

    # قطع sessionهای دیگر روی دیتابیس (برای restore تمیزتر)
    try:
        import subprocess
        params = _db_params()
        term_sql = (
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{params['name']}' AND pid <> pg_backend_pid();"
        )
        subprocess.run(
            [
                "psql",
                "-h", params["host"],
                "-p", params["port"],
                "-U", params["user"],
                "-d", "postgres",
                "-c", term_sql,
            ],
            env=_pg_env(),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        pass

    suffix = "".join(path.suffixes).lower()
    params = _db_params()
    env = _pg_env()

    try:
        if (
            suffix.endswith(".dump")
            or suffix.endswith(".backup")
            or path.suffix.lower() == ".dump"
            or path.name.endswith(".dump")
        ):
            if not _which_pg("pg_restore"):
                return False, "❌ ابزار <code>pg_restore</code> نصب نیست."
            cmd = [
                "pg_restore",
                "-h", params["host"],
                "-p", params["port"],
                "-U", params["user"],
                "-d", params["name"],
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-acl",
                str(path),
            ]
            proc = __import__("subprocess").run(
                cmd, env=env, capture_output=True, text=True, timeout=900,
            )
            # pg_restore اغلب با warning کد ۱ می‌دهد
            if proc.returncode not in (0, 1):
                err = (proc.stderr or proc.stdout or "").strip()[:800]
                return False, f"❌ pg_restore شکست خورد (code={proc.returncode}):\n<code>{err}</code>"
            warn = (proc.stderr or "").strip()
            extra = f"\n\n⚠️ هشدارها:\n<code>{warn[:400]}</code>" if warn and proc.returncode == 1 else ""
            return True, f"✅ بازیابی با موفقیت انجام شد.{extra}"

        # SQL plain / gzip
        if not _which_pg("psql"):
            return False, "❌ ابزار <code>psql</code> نصب نیست."

        import gzip
        import subprocess

        if suffix.endswith(".sql.gz") or path.name.endswith(".gz"):
            sql_bytes = gzip.open(path, "rb").read()
        else:
            sql_bytes = path.read_bytes()

        proc = subprocess.run(
            [
                "psql",
                "-h", params["host"],
                "-p", params["port"],
                "-U", params["user"],
                "-d", params["name"],
                "-v", "ON_ERROR_STOP=1",
            ],
            input=sql_bytes,
            env=env,
            capture_output=True,
            timeout=900,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace").strip()[:800]
            return False, f"❌ psql شکست خورد:\n<code>{err}</code>"
        return True, "✅ بازیابی SQL با موفقیت انجام شد."
    except Exception as e:
        logger.exception("restore failed")
        return False, f"❌ خطا در بازیابی: {e}"
    finally:
        try:
            from django.db import connections
            connections.close_all()
        except Exception:
            pass


create_dump = sync_to_async(create_dump_sync, thread_sensitive=False)
restore_dump = sync_to_async(restore_dump_sync, thread_sensitive=False)


def format_size(path: Path) -> str:
    n = path.stat().st_size
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


async def send_dump_to_owner(
    bot: Bot,
    *,
    reason: str = "manual",
    chat_id: int | None = None,
) -> tuple[bool, str]:
    """
    دامپ می‌سازد و به پیوی مالک (یا chat_id) می‌فرستد.
    reason: auto | manual
    """
    target = chat_id or CREATOR_USER_ID
    path, msg = await create_dump()
    if not path:
        try:
            await bot.send_message(target, msg, parse_mode="HTML")
        except Exception as e:
            logger.warning("notify dump fail: %s", e)
        return False, msg

    label = "خودکار (هر ۳ ساعت)" if reason == "auto" else "دستی"
    caption = (
        f"💾 <b>بکاپ دیتابیس تاسینو</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 نوع: {label}\n"
        f"📦 حجم: <b>{format_size(path)}</b>\n"
        f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"برای بازیابی: در پنل سازنده «بازیابی» را بزن و همین فایل را بفرست."
    )
    try:
        await bot.send_document(
            target,
            FSInputFile(path, filename=path.name),
            caption=caption,
            parse_mode="HTML",
        )
        return True, f"✅ دامپ ارسال شد ({format_size(path)})"
    except Exception as e:
        logger.exception("send dump failed")
        err = f"❌ ارسال فایل شکست خورد: {e}"
        try:
            await bot.send_message(target, err, parse_mode="HTML")
        except Exception:
            pass
        return False, err


async def send_auto_backup(bot: Bot) -> None:
    """جاب زمان‌بندی‌شده — هر ۳ ساعت."""
    logger.info("شروع بکاپ خودکار دیتابیس…")
    ok, msg = await send_dump_to_owner(bot, reason="auto")
    logger.info("بکاپ خودکار: %s | %s", "OK" if ok else "FAIL", msg)


def is_backup_document(filename: str | None) -> bool:
    if not filename:
        return False
    name = filename.lower()
    return (
        name.endswith(".dump")
        or name.endswith(".backup")
        or name.endswith(".sql")
        or name.endswith(".sql.gz")
        or name.startswith("tasino_backup_")
    )


async def save_incoming_document(bot: Bot, document, filename: str | None = None) -> Path:
    """دانلود فایل دامپ از تلگرام به پوشه موقت."""
    _ensure_dir()
    raw_name = filename or getattr(document, "file_name", None) or "restore.dump"
    safe = "".join(c for c in raw_name if c.isalnum() or c in "._-") or "restore.dump"
    if not any(safe.lower().endswith(ext) for ext in (".dump", ".backup", ".sql", ".gz")):
        safe += DUMP_SUFFIX
    dest = BACKUP_DIR / f"restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe}"
    await bot.download(document, destination=dest)
    return dest
