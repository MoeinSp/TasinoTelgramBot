"""تم‌های نمایش جدول لیگ (۱ تا ۱۰)."""
from __future__ import annotations

from dataclasses import dataclass, field

BOARD_MAX_CHARS = 1500
COMPACT_FALLBACK_THEME = 9

LEAGUE_THEME_NAMES: dict[int, str] = {
    1: "سکوی کلاسیک",
    2: "کارت باکس",
    3: "مینیمال",
    4: "نوار پیشرفت",
    5: "جدول ستونی",
    6: "جشن و هیجان",
    7: "فلش‌دار",
    8: "خط‌دوطرفه",
    9: "مدال فشرده",
    10: "بنر ستاره‌ای",
}


@dataclass
class LeaderRow:
    rank: int
    name: str
    wager: int
    tier: str
    badge: str
    prize_label: str = ""
    prize_paid_note: str = ""
    progress_pct: int = 0
    progress_note: str = ""


@dataclass
class BoardContext:
    title: str
    deadline: str
    prizes_line: str
    leaders: list[LeaderRow] = field(default_factory=list)
    viewer: LeaderRow | None = None
    page: int = 1
    pages: int = 1
    total: int = 0
    empty_text: tuple[str, str] = (
        "📭 هنوز کسی در لیگ این هفته شرط نزده.",
        "با اولین شرط، نامت اینجا ظاهر می‌شود 💪",
    )
    footer_note: str = ""


def clamp_theme(theme_id: int) -> int:
    try:
        t = int(theme_id or 1)
    except (TypeError, ValueError):
        t = 1
    return max(1, min(10, t))


def _medal(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "")


def _podium_title(rank: int) -> str:
    if rank == 1:
        return "👑 قهرمان هفته"
    if rank == 2:
        return "🥈 نفر دوم"
    if rank == 3:
        return "🥉 نفر سوم"
    return ""


def _prize_suffix(row: LeaderRow) -> str:
    if row.rank > 3 or not row.prize_label:
        return ""
    return f"\n   {row.prize_label}{row.prize_paid_note}"


def _progress_bar(pct: int, width: int = 10) -> str:
    pct = max(0, min(100, int(pct)))
    filled = int(round(pct * width / 100))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _header_full(ctx: BoardContext) -> list[str]:
    lines = [ctx.title, "┈" * 18]
    if ctx.deadline:
        lines.append(ctx.deadline)
    if ctx.prizes_line:
        lines.append("")
        lines.append(ctx.prizes_line)
    lines.append("")
    return lines


def _footer_full(ctx: BoardContext) -> list[str]:
    lines: list[str] = []
    if ctx.viewer is not None:
        v = ctx.viewer
        lines.extend(["", "┈" * 18, "📍 رتبه شما"])
        lines.append(
            f"🏷 #{v.rank} {v.name}\n"
            f"   📊 {v.wager:,} واحد\n"
            f"   {v.badge} {v.tier}"
        )
    if ctx.total > 0:
        lines.append("")
        if ctx.pages > 1:
            lines.append(f"📄 صفحه {ctx.page}/{ctx.pages}")
        lines.append(f"👥 {int(ctx.total):,} نفر در لیگ این هفته")
    if ctx.footer_note:
        lines.append(ctx.footer_note)
    return lines


def _tier_label(row: LeaderRow) -> str:
    return f"{row.badge} {row.tier}"


def _rest_line(row: LeaderRow) -> str:
    return f" {row.rank:2d} │ {row.name}  ·  {row.wager:,}  ·  {_tier_label(row)}"


def _rest_progress_line(row: LeaderRow) -> str:
    bar = _progress_bar(row.progress_pct, 8)
    return (
        f" {row.rank:2d} │ {row.name}  ·  {row.wager:,}  ·  {bar} {row.progress_pct}٪"
        f"  ·  {_tier_label(row)}"
    )


def _podium_classic(row: LeaderRow) -> list[str]:
    return [
        f"{_medal(row.rank)} {_podium_title(row.rank)}",
        f"   👤 {row.name}",
        f"   📊 {row.wager:,} واحد",
        f"   {_tier_label(row)}{_prize_suffix(row)}",
        "",
    ]


def _podium_progress(row: LeaderRow) -> list[str]:
    bar = _progress_bar(row.progress_pct, 10)
    return [
        f"      {_medal(row.rank)} #{row.rank}",
        f"  {row.name}",
        f"  {row.wager:,} واحد",
        f"  {bar} {row.progress_pct}٪",
        f"  {row.progress_note}",
        f"   {_tier_label(row)}{_prize_suffix(row)}",
        "",
    ]


def _split_podium_rest(ctx: BoardContext) -> tuple[list[LeaderRow], list[LeaderRow]]:
    podium = [r for r in ctx.leaders if r.rank <= 3]
    rest = [r for r in ctx.leaders if r.rank > 3]
    return podium, rest


def _theme_1_classic(ctx: BoardContext) -> list[str]:
    lines = _header_full(ctx)
    if not ctx.leaders:
        lines.extend(ctx.empty_text)
        return lines
    podium, rest = _split_podium_rest(ctx)
    if podium:
        lines.extend(["🏛 سکوی برترها", "┈" * 18])
        for row in podium:
            lines.extend(_podium_classic(row))
    if rest:
        lines.extend(["📋 ادامه جدول", "┈" * 18])
        for row in rest:
            lines.append(_rest_line(row))
    lines.extend(_footer_full(ctx))
    return lines


def _theme_2_box(ctx: BoardContext) -> list[str]:
    lines = [
        "╔══════════════════════════╗",
        "║   🏆  رتبه‌برترهای لیگ   ║",
        "╚══════════════════════════╝",
    ]
    if ctx.deadline:
        lines.append(ctx.deadline)
    if ctx.prizes_line:
        lines.append(ctx.prizes_line)
    lines.append("")
    if not ctx.leaders:
        lines.extend(ctx.empty_text)
        return lines
    podium, rest = _split_podium_rest(ctx)
    for row in podium:
        lines.extend([
            "┏━━━━━━━━━━━━━━━━━━━━━━┓",
            f"┃ {_medal(row.rank)}  #{row.rank}  {row.name[:14]:<14}┃",
            f"┃ 📊 {row.wager:,}  ·  {row.badge} {row.tier[:10]:<10}┃",
        ])
        if row.prize_label:
            lines.append(f"┃ 🎁 {row.prize_label[:20]:<20}┃")
        lines.append("┗━━━━━━━━━━━━━━━━━━━━━━┛")
        lines.append("")
    for row in rest:
        lines.append(f"▸ #{row.rank}  {row.name}  ·  {row.wager:,}  ·  {_tier_label(row)}")
    lines.extend(_footer_full(ctx))
    return lines


def _theme_3_minimal(ctx: BoardContext) -> list[str]:
    lines = _header_full(ctx)
    if not ctx.leaders:
        lines.extend(ctx.empty_text)
        return lines
    for row in ctx.leaders:
        m = _medal(row.rank) or f"{row.rank}."
        prize = f"  {row.prize_label}" if row.rank <= 3 and row.prize_label else ""
        lines.append(f"{m} {row.name:<16} {row.wager:>7,}  {row.badge} {row.tier[:8]}{prize}")
    lines.extend(_footer_full(ctx))
    return lines


def _theme_4_progress(ctx: BoardContext) -> list[str]:
    lines = _header_full(ctx)
    if not ctx.leaders:
        lines.extend(ctx.empty_text)
        return lines
    podium, rest = _split_podium_rest(ctx)
    for row in podium:
        lines.extend(_podium_progress(row))
    if rest:
        lines.extend(["📋 ادامه جدول", "┈" * 18])
        for row in rest:
            lines.append(_rest_progress_line(row))
    lines.extend(_footer_full(ctx))
    return lines


def _theme_5_table(ctx: BoardContext) -> list[str]:
    lines = _header_full(ctx)
    if not ctx.leaders:
        lines.extend(ctx.empty_text)
        return lines
    lines.append("رتبه │ نام            │ حجم      │ پله")
    lines.append("─────┼────────────────┼──────────┼──────────")
    for row in ctx.leaders:
        m = _medal(row.rank) or f" {row.rank:2d} "
        prize = f" │ {row.prize_label}" if row.rank <= 3 and row.prize_label else ""
        lines.append(
            f" {m} │ {row.name[:14]:<14} │ {row.wager:>7,} │ {row.badge} {row.tier[:8]}{prize}"
        )
    lines.extend(_footer_full(ctx))
    return lines


def _theme_6_celebration(ctx: BoardContext) -> list[str]:
    lines = [
        "✨✨✨✨✨✨✨✨",
        "     🏆  قهرمانان هفته  🏆",
        "✨✨✨✨✨✨✨✨",
        "",
    ]
    if ctx.deadline:
        lines.append(ctx.deadline)
    if ctx.prizes_line:
        lines.append(ctx.prizes_line)
        lines.append("")
    if not ctx.leaders:
        lines.extend(ctx.empty_text)
        return lines
    cheers = {1: "تاج این هفته مال توئه 👑", 2: "یک پله تا تاج 🔥", 3: "سکوی برترها 💪"}
    podium, rest = _split_podium_rest(ctx)
    for row in podium:
        label = {1: "قهرمان", 2: "نقره", 3: "برنز"}.get(row.rank, "")
        lines.extend([
            f"{_medal(row.rank)} {label} → {row.name}",
            f"   💰 {row.wager:,} واحد · {row.badge} {row.tier}",
        ])
        if row.prize_label:
            lines.append(f"   {row.prize_label}{row.prize_paid_note}")
        lines.append(f"   «{cheers.get(row.rank, '')}»")
        lines.append("")
    for row in rest:
        lines.append(f"#{row.rank} {row.name} · {row.wager:,} · {_tier_label(row)}")
    lines.extend(_footer_full(ctx))
    return lines


def _theme_7_arrows(ctx: BoardContext) -> list[str]:
    lines = _header_full(ctx)
    if not ctx.leaders:
        lines.extend(ctx.empty_text)
        return lines
    podium, rest = _split_podium_rest(ctx)
    for row in podium:
        lines.extend([
            f"▸ {_medal(row.rank)} {row.name}",
            f"   {row.wager:,} واحد · {row.badge} {row.tier}{_prize_suffix(row)}",
            "",
        ])
    for row in rest:
        m = _medal(row.rank) or f"#{row.rank}"
        lines.append(f"▸ {m} {row.name:<14} {row.wager:>7,} · {_tier_label(row)}")
    lines.extend(_footer_full(ctx))
    return lines


def _theme_8_double_line(ctx: BoardContext) -> list[str]:
    lines = _header_full(ctx)
    if not ctx.leaders:
        lines.extend(ctx.empty_text)
        return lines
    podium, rest = _split_podium_rest(ctx)
    if podium:
        lines.extend(["🏛 سکوی برترها", "━━━━━━━━━━━━━━━━━━━━"])
    for row in podium:
        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━",
            f"{_medal(row.rank)}  {row.name}  —  {row.wager:,} واحد",
            f"   {_tier_label(row)}{_prize_suffix(row)}",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
        ])
    if rest:
        lines.append("📋 ادامه")
        for row in rest:
            lines.append(f"━━ #{row.rank} {row.name} · {row.wager:,} · {_tier_label(row)}")
    lines.extend(_footer_full(ctx))
    return lines


def _theme_9_compact_medal(ctx: BoardContext) -> list[str]:
    lines = _header_full(ctx)
    if not ctx.leaders:
        lines.extend(ctx.empty_text)
        return lines
    for row in ctx.leaders:
        m = _medal(row.rank) or f"#{row.rank}"
        prize = f" {row.prize_label}" if row.rank <= 3 and row.prize_label else ""
        lines.append(f"{m} {row.name} │ {row.wager:,} │ {_tier_label(row)}{prize}")
    lines.extend(_footer_full(ctx))
    return lines


def _theme_10_star_banner(ctx: BoardContext) -> list[str]:
    lines = [
        "⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐",
        f"   {ctx.title}",
        "⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐",
    ]
    if ctx.deadline:
        lines.append(ctx.deadline)
    if ctx.prizes_line:
        lines.append(ctx.prizes_line)
    lines.append("")
    if not ctx.leaders:
        lines.extend(ctx.empty_text)
        return lines
    podium, rest = _split_podium_rest(ctx)
    for row in podium:
        if row.rank == 1:
            lines.extend([
                "        👑",
                f"       🥇 #{row.rank}",
                f"    {row.name}",
                f"   {row.wager:,} واحد",
                f"   {_tier_label(row)}{_prize_suffix(row)}",
                "",
            ])
        else:
            lines.extend([
                f"      {_medal(row.rank)} #{row.rank}  {row.name}",
                f"      {row.wager:,} · {_tier_label(row)}{_prize_suffix(row)}",
                "",
            ])
    for row in rest:
        lines.append(f"  {row.rank:2d}. {row.name}  ·  {row.wager:,}  ·  {_tier_label(row)}")
    lines.extend(_footer_full(ctx))
    return lines


_THEME_RENDERERS = {
    1: _theme_1_classic,
    2: _theme_2_box,
    3: _theme_3_minimal,
    4: _theme_4_progress,
    5: _theme_5_table,
    6: _theme_6_celebration,
    7: _theme_7_arrows,
    8: _theme_8_double_line,
    9: _theme_9_compact_medal,
    10: _theme_10_star_banner,
}


def _render_raw(theme_id: int, ctx: BoardContext) -> str:
    tid = clamp_theme(theme_id)
    renderer = _THEME_RENDERERS.get(tid, _theme_1_classic)
    return "\n".join(renderer(ctx))


def _trim_for_length(ctx: BoardContext, theme_id: int, max_chars: int) -> str:
    """اول رتبه ۴+ کم می‌شود — سکوی ۳ نفر اول زیبا می‌ماند."""
    tid = clamp_theme(theme_id)
    original_total = ctx.total

    def _render() -> str:
        return _render_raw(tid, ctx)

    text = _render()
    if len(text) <= max_chars:
        return text

    while len(text) > max_chars:
        rest = [r for r in ctx.leaders if r.rank > 3]
        if len(rest) > 0:
            ctx.leaders = [r for r in ctx.leaders if r.rank <= 3] + rest[:-1]
            ctx.total = original_total
            text = _render()
            continue
        shortened = False
        for row in ctx.leaders:
            if len(row.name) > 12:
                row.name = row.name[:11] + "…"
                shortened = True
        if shortened:
            text = _render()
            if len(text) <= max_chars:
                return text
        break

    if len(text) <= max_chars:
        return text

    if tid != COMPACT_FALLBACK_THEME:
        text = _render_raw(COMPACT_FALLBACK_THEME, ctx)
        if len(text) <= max_chars:
            return text

    if tid != 3:
        text = _render_raw(3, ctx)
        if len(text) <= max_chars:
            return text

    if len(text) > max_chars:
        text = text[: max_chars - 24].rstrip() + "\n… (ادامه در لیگ 2)"
    return text


def render_league_board(theme_id: int, ctx: BoardContext, *, max_chars: int = BOARD_MAX_CHARS) -> str:
    return _trim_for_length(ctx, theme_id, max_chars)


def format_theme_catalog() -> str:
    lines = ["🎨 تم‌های جدول لیگ", "━━━━━━━━━━━━━━━━━━━━"]
    for i in range(1, 11):
        lines.append(f"تم {i}: {LEAGUE_THEME_NAMES[i]}")
    lines.append("")
    lines.append("تغییر: تم لیگ 1 … تم لیگ 10")
    lines.append("پیش‌نمایش: لیگ نمونه")
    lines.append("وضعیت: تم لیگ وضعیت")
    return "\n".join(lines)


def make_sample_leaders(*, count: int = 10) -> list[dict]:
    samples = [
        ("علی رضایی", 45_000, "لیگ طلایی"),
        ("محمد کریمی", 38_200, "لیگ طلایی"),
        ("سارا احمدی", 31_500, "لیگ نقره‌ای"),
        ("رضا موسوی", 28_900, "لیگ نقره‌ای"),
        ("امیر حسینی", 24_100, "لیگ نقره‌ای"),
        ("نازنین جعفری", 19_800, "لیگ برنزی"),
        ("پویا نوری", 16_500, "لیگ برنزی"),
        ("مهدی صادقی", 14_200, "لیگ برنزی"),
        ("فاطمه رحمانی", 11_900, "لیگ برنزی"),
        ("کامران باقری", 9_600, "لیگ برنزی"),
    ]
    out = []
    for i, (_name, wager, tier) in enumerate(samples[:count], 1):
        out.append({
            "rank": i,
            "user_id": f"sample_{i}",
            "wager_total": wager,
            "tier_name": tier,
        })
    return out
