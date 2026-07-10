"""
کیبورد و صفحات راهنمای پیوی — فقط راهنما (بدون تغییر تنظیمات)
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton as B

from bot.group_help import PAGES, get_page

HELP_HOME_TEXT = (
    "📚 <b>راهنمای ربات — صفحه اصلی</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "بخش مورد نظر را انتخاب کنید تا دستورات همان قسمت را ببینید.\n\n"
    "<i>💡 این منو فقط راهنماست و تنظیمات گروه را تغییر نمی‌دهد.</i>"
)


def _h(code: str, label: str) -> B:
    return B(text=label, callback_data=f"h:{code}")


def _back(to: str = "0", label: str = "بازگشت ◀️") -> B:
    return B(text=label, callback_data=f"h:{to}")


def help_home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_h("1", "• مدیریت قفل‌ها")],
        [_h("7", "• تنظیمات گروه"), _h("antispam", "• ضد اسپم و فلود")],
        [_h("2.7", "• پنل کاربر"), _h("punish", "• مجازات کاربران")],
        [_h("2.2", "• ارتقا و عزل کاربران")],
        [_h("5", "• فیلتر کلمات"), _h("purge", "• پاکسازی")],
        [_h("welcome", "• خوش‌آمدگویی"), _h("security", "• کپچا و امنیت")],
        [_h("4.3", "• آمار فعالیت‌ها"), _h("4.2", "• سرگرمی و کاربردی")],
        [_h("4", "• تاس و بازی‌ها"), _h("8", "• مالی و کیف پول")],
        [_h("6", "• سخنگو و یادگیری"), _h("2", "• مدیریت اعضا")],
        [_h("3", "• سیستم اخطار")],
        [B(text="🏠 بازگشت به منوی اصلی", callback_data="h:home")],
    ])


def help_locks_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_h("1", "• معرفی قفل‌ها")],
        [_h("1.1", "• قفل‌های جداگانه")],
        [_h("1.2", "• قفل کل گروه")],
        [_back("0")],
    ])


def help_members_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_h("2.1", "• مالکیت"), _h("2.2", "• ادمین‌ها")],
        [_h("2.3", "• اعضای ویژه"), _h("2.6", "• تگ همگانی")],
        [_h("2.7", "• لقب و مشخصات")],
        [_back("0")],
    ])


def help_punish_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_h("3", "• سیستم اخطار")],
        [_h("2.4", "• بن و اخراج"), _h("2.5", "• سکوت")],
        [_back("0")],
    ])


def help_games_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_h("4.1", "• تاس و مسابقه")],
        [_h("4.2", "• سایر بازی‌ها و سرگرمی")],
        [_h("4.3", "• آمار بازی‌ها"), _h("4.4", "• تنظیمات بازی")],
        [_back("0")],
    ])


def help_finance_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_h("8.1", "• موجودی"), _h("8.2", "• شماره کارت")],
        [_h("8.3", "• گزارش و تسویه"), _h("8.4", "• حق واسطه")],
        [_back("0")],
    ])


def help_learn_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_h("6.1", "• سخنگو"), _h("6.2", "• یادگیری")],
        [_h("6.3", "• مشخصات کاربران")],
        [_back("0")],
    ])


def help_page_kb(code: str) -> InlineKeyboardMarkup:
    """کیبورد مناسب هر صفحه راهنما."""
    if code in ("0", ""):
        return help_home_kb()
    if code == "1":
        return help_locks_kb()
    if code == "2":
        return help_members_kb()
    if code == "punish":
        return help_punish_kb()
    if code == "4":
        return help_games_kb()
    if code == "8":
        return help_finance_kb()
    if code == "6":
        return help_learn_kb()
    # صفحات جزئی → بازگشت به دسته والد
    parent = "0"
    if code.startswith("1."):
        parent = "1"
    elif code.startswith("2."):
        parent = "2"
    elif code.startswith("4."):
        parent = "4"
    elif code.startswith("6."):
        parent = "6"
    elif code.startswith("8."):
        parent = "8"
    elif code in ("3", "2.4", "2.5"):
        parent = "punish"
    return InlineKeyboardMarkup(inline_keyboard=[[_back(parent)]])


PAGE_PURGE = """\
─────────────────────
<b>🧹  پاکسازی</b>
─────────────────────

حذف پیام‌ها:
◾ <code>پاکسازی</code> — ریپلای روی پیام مبدأ، حذف تا همان پیام
◾ <code>پاکسازی 100</code> — حذف ۱۰۰ پیام آخر (حداکثر ۳۰۰)

پاکسازی لیست‌ها:
◾ <code>پاکسازی لیست ویژه</code>
◾ <code>پاکسازی لیست بن</code>
◾ <code>پاکسازی لیست سکوت</code>

<i>💡 فقط ادمین/مالک می‌تواند پاکسازی کند.</i>"""


PAGE_WELCOME = """\
─────────────────────
<b>🎉  خوش‌آمدگویی</b>
─────────────────────

◾ <code>خوشامد روشن</code> / <code>خوشامد خاموش</code>
◾ <code>تنظیم خوشامد [متن]</code> — متن خوشامد
◾ <code>تنظیم گیف خوشامد</code> — ریپلای روی گیف
◾ <code>حذف گیف خوشامد</code>
◾ <code>وضعیت خوشامد</code>

متغیرهای متن:
◾ <code>{mention}</code> — منشن عضو جدید
◾ <code>{group}</code> — نام گروه

<i>💡 پیش‌فرض خوشامدگویی روشن است.</i>"""


PAGE_ANTISPAM = """\
─────────────────────
<b>🛡  ضد اسپم و فلود</b>
─────────────────────

آنتی‌فلود:
◾ <code>فلود روشن</code> / <code>فلود خاموش</code>
◾ جلوگیری از ارسال پشت‌سرهم پیام

ضد رید:
◾ <code>ضد رید روشن</code> / <code>ضد رید خاموش</code>
◾ اخراج فوری اعضای جدید در حمله گروهی

قفل‌های مرتبط:
◾ <code>قفل لینک</code> · <code>قفل فوروارد</code>
◾ <code>قفل اینلاین</code> · <code>قفل کلمات</code>

<i>💡 برای جزئیات قفل‌ها به بخش «مدیریت قفل‌ها» بروید.</i>"""


PAGE_SECURITY = """\
─────────────────────
<b>🔐  کپچا و امنیت</b>
─────────────────────

کپچا (تایید اعضای جدید):
◾ <code>کپچا روشن</code> / <code>کپچا خاموش</code>
◾ عضو جدید تا تایید دکمه، محدود می‌ماند

حالت شب:
◾ <code>حالت شب روشن 23 7</code> — قفل از ۲۳ تا ۷
◾ <code>حالت شب خاموش</code>

قفل کل گروه:
◾ <code>قفل گروه</code> / <code>باز کردن گروه</code>

کانال لاگ:
◾ <code>تنظیم کانال لاگ [شناسه]</code>
◾ <code>حذف کانال لاگ</code>

<i>💡 کپچا و ضد رید را از پنل تنظیمات گروه هم می‌توانید مدیریت کنید.</i>"""


_EXTRA_PAGES = {
    "purge": PAGE_PURGE,
    "welcome": PAGE_WELCOME,
    "antispam": PAGE_ANTISPAM,
    "security": PAGE_SECURITY,
    "punish": (
        "─────────────────────\n"
        "<b>⚖️  مجازات کاربران</b>\n"
        "─────────────────────\n\n"
        "از دکمه‌های زیر بخش مورد نظر را انتخاب کنید:\n"
        "◾ سیستم اخطار\n"
        "◾ بن و اخراج\n"
        "◾ سکوت"
    ),
}


def get_help_content(code: str) -> tuple[str, InlineKeyboardMarkup]:
    """متن + کیبورد راهنما برای کد صفحه."""
    if code in ("0", "", "main"):
        return HELP_HOME_TEXT, help_home_kb()

    if code in _EXTRA_PAGES:
        return _EXTRA_PAGES[code], help_page_kb(code)

    # منوهای دسته که خودشان زیر‌منو دارند
    if code == "1":
        text = PAGES.get("1", HELP_HOME_TEXT)
        return text, help_locks_kb()
    if code == "2":
        text = PAGES.get("2", HELP_HOME_TEXT)
        return text, help_members_kb()
    if code == "4":
        text = PAGES.get("4", HELP_HOME_TEXT)
        return text, help_games_kb()
    if code == "6":
        text = PAGES.get("6", HELP_HOME_TEXT)
        return text, help_learn_kb()
    if code == "8":
        text = PAGES.get("8", HELP_HOME_TEXT)
        return text, help_finance_kb()

    page = get_page(code)
    if page:
        return page, help_page_kb(code)

    return HELP_HOME_TEXT, help_home_kb()
