OWNER_CACHE: dict[int, int] = {}            # chat_id → user_id
ADMINS_CACHE: dict[int, set[int]] = {}     # chat_id → set of user_ids
VIP_USERS_CACHE: dict[int, set[int]] = {}  # chat_id → set of user_ids
SPEAKER_ON: set[int] = set()               # chat_ids with speaker on
OFF_GROUP: set[int] = set()                # chat_ids with bot off
GROUP_LOCK: set[int] = set()               # chat_ids with global lock
WARNING_ENABLED: set[int] = set()          # chat_ids with auto-warn on
DICE_OPTION: set[int] = set()              # chat_ids with dice tracking
LEARNED_RESPONSES: dict[int, dict[str, str]] = {}  # chat_id → {trigger: response}
WORD_FILTERS: dict[int, list[str]] = {}    # chat_id → words list
GROUP_LOCKS: dict[int, dict] = {}          # chat_id → locks dict

MUTED_USERS: dict[int, set[int]] = {}      # chat_id → set of muted user_ids

CACHE_LOADED = False
