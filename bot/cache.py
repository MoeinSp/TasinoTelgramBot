OWNER_CACHE: dict[int, int] = {}            # chat_id → creator تلگرام (مالک)
TG_ADMINS_CACHE: dict[int, set[int]] = {}  # chat_id → ادمین‌های واقعی تلگرام
ADMINS_CACHE: dict[int, set[int]] = {}     # chat_id → ادمین‌های ربات
VIP_USERS_CACHE: dict[int, set[int]] = {}  # chat_id → set of user_ids
SPEAKER_ON: set[int] = set()               # chat_ids with speaker on
OFF_GROUP: set[int] = set()                # chat_ids with bot off
GROUP_LOCK: set[int] = set()               # chat_ids with global lock
WARNING_ENABLED: set[int] = set()          # chat_ids with auto-warn on
DICE_OPTION: set[int] = set()              # chat_ids with dice tracking
DICE_TURN_LIMIT: dict[int, int] = {}       # chat_id → max roll turns (0 = off)
LEARNED_RESPONSES: dict[int, dict[str, str]] = {}  # chat_id → {trigger: response}
WORD_FILTERS: dict[int, list[str]] = {}    # chat_id → words list
GROUP_LOCKS: dict[int, dict] = {}          # chat_id → locks dict

MUTED_USERS: dict[int, set[int]] = {}      # chat_id → set of muted user_ids

# خوشامدگویی پیش‌فرض روشنه — این ست فقط گروه‌هایی که صراحتاً خاموشش کردن رو نگه می‌داره
WELCOME_DISABLED: set[int] = set()
WELCOME_SETTINGS: dict[int, dict] = {}    # chat_id → {"text": str, "gif_file_id": str}

PENDING_SETUP_MSG: dict[int, int] = {}    # chat_id → message_id پیام «منتظر ادمین شدن»

ANTI_FLOOD_ENABLED: set[int] = set()
ANTI_FLOOD_SETTINGS: dict[int, dict] = {} # chat_id → {"limit": int, "window": int}
FLOOD_TRACKER: dict[tuple, list] = {}     # (chat_id, user_id) → [timestamps]

# ─── کپچا ──────────────────────────────────────────────────────────────────
CAPTCHA_ENABLED: set[int] = set()          # chat_ids که کپچا براشون فعاله (پیش‌فرض: خاموش)
CAPTCHA_TIMEOUT: dict[int, int] = {}       # chat_id → مهلت به ثانیه
PENDING_CAPTCHA: dict[tuple, dict] = {}    # (chat_id, user_id) → {"message_id": int, "task": asyncio.Task}

# ─── ضد رید ────────────────────────────────────────────────────────────────
ANTIRAID_ENABLED: set[int] = set()         # chat_ids که حالت ضد رید موقتاً فعاله

# ─── حالت شب ───────────────────────────────────────────────────────────────
NIGHT_MODE: dict[int, tuple[int, int]] = {}  # chat_id → (ساعت شروع، ساعت پایان)

# ─── ایموجی متحرک تلگرام (بازی‌ها) ─────────────────────────────────────────
TELEGRAM_EMOJI_ON: set[int] = set()        # پیش‌فرض: خاموش → بازی متنی مثل rubpy

# ─── دستورات ویژه سازنده (فقط برای یک user_id) ──────────────────────────────
SILENCE_ALL: set[int] = set()              # chat_ids که «خفه» فعال است
SILENCE_ALL_USERS: dict[int, set[int]] = {}  # chat_id → user_ids محدودشده در خفه

# ─── کانال لاگ ────────────────────────────────────────────────────────────
LOG_CHANNEL: dict[int, int] = {}           # chat_id → log_channel_id

# ─── جوین اجباری کانال (پیوی) ─────────────────────────────────────────────
FORCED_JOIN: dict = {
    "enabled": False,
    "channel_id": None,
    "channel_title": "",
    "channel_username": "",
    "invite_link": "",
}
FORCED_JOIN_MEMBER_CHECK: dict[tuple[int, int], tuple[bool, float]] = {}

# ─── تنظیمات سراسری سایت/ربات ─────────────────────────────────────────────
SITE_CONFIG: dict = {
    "link_directory_url": "https://t.me/TasinoBot",
    "link_directory_title": "🔥 بزرگترین لینکدونی",
    "support_url": "https://t.me/Spayers",
    "support_title": "گروه پشتیبانی",
    "channel_url": "https://t.me/TasinoBot",
}

# ─── پنل پیوی (گروه انتخاب‌شده برای تنظیمات) ───────────────────────────────
PV_PANEL_GROUP: dict[int, int] = {}        # user_id → group chat_id

CACHE_LOADED = False
