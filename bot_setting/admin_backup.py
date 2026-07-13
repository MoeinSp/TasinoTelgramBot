"""
پنل ادمین جنگو — بکاپ و بازیابی PostgreSQL + کنترل روشن/خاموش سراسری ربات.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime
from pathlib import Path

from django.contrib import admin, messages
from django.http import FileResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from unfold.admin import ModelAdmin

from bot.backup import (
    BACKUP_DIR,
    DUMP_SUFFIX,
    create_dump_sync,
    format_size,
    restore_dump_sync,
    _ensure_dir,
)
from .models import BotSiteConfig, DatabaseBackupTool

logger = logging.getLogger(__name__)

PENDING_ADMIN_RESTORE: dict[int, str] = {}


def _bot_status() -> dict:
    cfg = BotSiteConfig.get_singleton()
    return {
        "bot_enabled": bool(getattr(cfg, "bot_enabled", True)),
        "updated_at": cfg.updated_at,
    }


def _list_local_dumps(limit: int = 20) -> list[dict]:
    _ensure_dir()
    files = sorted(
        list(BACKUP_DIR.glob(f"*{DUMP_SUFFIX}"))
        + list(BACKUP_DIR.glob("*.sql"))
        + list(BACKUP_DIR.glob("*.sql.gz"))
        + list(BACKUP_DIR.glob("*.backup")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    out = []
    for p in files[:limit]:
        try:
            out.append({
                "name": p.name,
                "path": str(p),
                "size": format_size(p),
                "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
        except Exception:
            continue
    return out


@admin.register(DatabaseBackupTool)
class DatabaseBackupToolAdmin(ModelAdmin):
    change_list_template = "admin/bot_setting/backup_restore.html"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return request.user.is_staff

    def changelist_view(self, request, extra_context=None):
        status = _bot_status()
        pending = PENDING_ADMIN_RESTORE.get(request.user.id)
        ctx = {
            **self.admin_site.each_context(request),
            "title": "بکاپ و بازیابی دیتابیس",
            "bot_enabled": status["bot_enabled"],
            "bot_updated_at": status["updated_at"],
            "dumps": _list_local_dumps(),
            "pending_restore": Path(pending).name if pending else None,
            "opts": self.model._meta,
            "has_view_permission": True,
        }
        if extra_context:
            ctx.update(extra_context)
        return render(request, self.change_list_template, ctx)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "toggle-bot/",
                self.admin_site.admin_view(self.toggle_bot_view),
                name="bot_setting_databasebackuptool_toggle_bot",
            ),
            path(
                "create-dump/",
                self.admin_site.admin_view(self.create_dump_view),
                name="bot_setting_databasebackuptool_create_dump",
            ),
            path(
                "download/<str:filename>/",
                self.admin_site.admin_view(self.download_view),
                name="bot_setting_databasebackuptool_download",
            ),
            path(
                "upload-restore/",
                self.admin_site.admin_view(self.upload_restore_view),
                name="bot_setting_databasebackuptool_upload_restore",
            ),
            path(
                "confirm-restore/",
                self.admin_site.admin_view(self.confirm_restore_view),
                name="bot_setting_databasebackuptool_confirm_restore",
            ),
            path(
                "cancel-restore/",
                self.admin_site.admin_view(self.cancel_restore_view),
                name="bot_setting_databasebackuptool_cancel_restore",
            ),
            path(
                "restore-local/<str:filename>/",
                self.admin_site.admin_view(self.restore_local_view),
                name="bot_setting_databasebackuptool_restore_local",
            ),
        ]
        return custom + urls

    def _redirect_self(self):
        return HttpResponseRedirect(
            reverse("admin:bot_setting_databasebackuptool_changelist")
        )

    def toggle_bot_view(self, request):
        if request.method != "POST":
            return self._redirect_self()
        cfg = BotSiteConfig.get_singleton()
        cfg.bot_enabled = not bool(cfg.bot_enabled)
        cfg.save(update_fields=["bot_enabled", "updated_at"])
        try:
            from bot.site_config import apply_site_config_cache, _site_snapshot
            apply_site_config_cache(_site_snapshot(cfg))
        except Exception:
            pass
        if cfg.bot_enabled:
            messages.success(request, "🟢 ربات سراسری روشن شد.")
        else:
            messages.warning(
                request,
                "⚫ ربات سراسری خاموش شد. الان می‌توانید بکاپ/بازیابی کنید.",
            )
        return self._redirect_self()

    def create_dump_view(self, request):
        if request.method != "POST":
            return self._redirect_self()
        path, msg = create_dump_sync()
        if path:
            messages.success(request, f"دامپ ساخته شد: {path.name} — {format_size(path)}")
        else:
            clean = msg.replace("<code>", "").replace("</code>", "")
            messages.error(request, html.unescape(clean))
        return self._redirect_self()

    def download_view(self, request, filename: str):
        safe = Path(filename).name
        path = BACKUP_DIR / safe
        if not path.exists() or not path.is_file():
            messages.error(request, "فایل پیدا نشد.")
            return self._redirect_self()
        return FileResponse(path.open("rb"), as_attachment=True, filename=safe)

    def upload_restore_view(self, request):
        if request.method != "POST":
            return self._redirect_self()
        uploaded = request.FILES.get("dump_file")
        if not uploaded:
            messages.error(request, "فایلی انتخاب نشده.")
            return self._redirect_self()
        name = Path(uploaded.name).name
        lower = name.lower()
        if not any(lower.endswith(ext) for ext in (".dump", ".backup", ".sql", ".sql.gz", ".gz")):
            messages.error(request, "فرمت مجاز: .dump / .backup / .sql / .sql.gz")
            return self._redirect_self()
        _ensure_dir()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = BACKUP_DIR / f"upload_{stamp}_{name}"
        with dest.open("wb") as f:
            for chunk in uploaded.chunks():
                f.write(chunk)
        PENDING_ADMIN_RESTORE[request.user.id] = str(dest)
        messages.warning(
            request,
            f"فایل «{dest.name}» آمادهٔ تأیید بازیابی است. "
            "حتماً ربات را خاموش کنید و روی «تأیید بازیابی» بزنید.",
        )
        return self._redirect_self()

    def restore_local_view(self, request, filename: str):
        if request.method != "POST":
            return self._redirect_self()
        safe = Path(filename).name
        path = BACKUP_DIR / safe
        if not path.exists():
            messages.error(request, "فایل محلی پیدا نشد.")
            return self._redirect_self()
        PENDING_ADMIN_RESTORE[request.user.id] = str(path)
        messages.warning(
            request,
            f"فایل «{safe}» برای بازیابی انتخاب شد. ربات را خاموش کنید و تأیید کنید.",
        )
        return self._redirect_self()

    def cancel_restore_view(self, request):
        PENDING_ADMIN_RESTORE.pop(request.user.id, None)
        messages.info(request, "بازیابی لغو شد.")
        return self._redirect_self()

    def confirm_restore_view(self, request):
        if request.method != "POST":
            return self._redirect_self()
        pending = PENDING_ADMIN_RESTORE.get(request.user.id)
        if not pending:
            messages.error(request, "فایل در انتظاری نیست.")
            return self._redirect_self()
        path = Path(pending)
        if not path.exists():
            PENDING_ADMIN_RESTORE.pop(request.user.id, None)
            messages.error(request, "فایل دامپ دیگر وجود ندارد.")
            return self._redirect_self()

        cfg = BotSiteConfig.get_singleton()
        if cfg.bot_enabled and request.POST.get("force") != "1":
            messages.error(
                request,
                "اول ربات را سراسری خاموش کنید، بعد دوباره تأیید کنید.",
            )
            return self._redirect_self()

        ok, msg = restore_dump_sync(path)
        PENDING_ADMIN_RESTORE.pop(request.user.id, None)
        clean = msg.replace("<code>", "").replace("</code>", "")
        if ok:
            messages.success(request, clean[:500])
            try:
                from asgiref.sync import async_to_sync
                from bot.cache_manager import load_all_caches
                async_to_sync(load_all_caches)()
            except Exception:
                pass
            messages.info(request, "پس از بازیابی موفق، ربات را دوباره روشن کنید.")
        else:
            messages.error(request, clean[:800])
        return self._redirect_self()
