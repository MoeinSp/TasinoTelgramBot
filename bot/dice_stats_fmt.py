"""فرمت فشرده آمار مسابقات تاس — تلگرام."""
from __future__ import annotations

TOP_N = 3
MAX_BET_GAMES = 5


def format_dice_game_stats(records, title: str, name_map: dict, *, prizes: dict | None = None) -> str:
    """name_map: user_id -> display name (HTML allowed)."""
    if not records:
        return f"<b>{title}</b>\n\n📭 مسابقه‌ای ثبت نشده."

    prizes = prizes or {}
    prize_games = int(prizes.get("prize_stat_games") or 0)
    prize_max_bet = int(prizes.get("prize_stat_max_bet") or 0)

    def _name(uid):
        return name_map.get(uid) or name_map.get(int(uid)) or f'<a href="tg://user?id={uid}">کاربر</a>'

    def _plabel(amount: int) -> str:
        if int(amount or 0) <= 0:
            return ""
        return f" · 🎁 {int(amount):,}"

    games_count: dict = {}
    win_count: dict = {}
    profit_sum: dict = {}
    sessions: dict[str, dict] = {}

    for rec in records:
        uid = rec.telegram_user_id
        games_count[uid] = games_count.get(uid, 0) + 1
        if rec.winner:
            win_count[uid] = win_count.get(uid, 0) + 1
        profit_sum[uid] = profit_sum.get(uid, 0) + int(rec.amount_won or 0)

        session = (rec.game_session or "").strip()
        bet = int(rec.bet_amount or 0)
        if session and bet > 0:
            bucket = sessions.setdefault(session, {"bet": bet, "players": set()})
            bucket["players"].add(uid)

    medals = ["🥇", "🥈", "🥉"]
    lines = [f"<b>{title}</b>", "━━━━━━━━━━━━━━━━"]
    if prize_games > 0 or prize_max_bet > 0:
        from bot.stat_prizes import format_daily_prizes_line
        lines.append(format_daily_prizes_line(prizes, html=True))

    top_wins = sorted(win_count.items(), key=lambda x: x[1], reverse=True)[:TOP_N]
    if top_wins:
        lines.append("")
        lines.append("<b>🏆 برترین‌ها · برد</b>")
        for i, (uid, n) in enumerate(top_wins):
            mark = medals[i] if i < len(medals) else f"{i + 1}."
            lines.append(f"{mark} {_name(uid)} — {n} برد")

    top_games = sorted(games_count.items(), key=lambda x: x[1], reverse=True)[:TOP_N]
    if top_games:
        lines.append("")
        lines.append(f"<b>🎮 پربازی‌ترین{_plabel(prize_games)}</b>")
        for i, (uid, n) in enumerate(top_games):
            mark = medals[i] if i < len(medals) else f"{i + 1}."
            lines.append(f"{mark} {_name(uid)} — {n} بازی")

    top_profit = [
        (uid, val)
        for uid, val in sorted(profit_sum.items(), key=lambda x: x[1], reverse=True)
        if val > 0
    ][:TOP_N]
    if top_profit:
        lines.append("")
        lines.append("<b>💰 بیشترین سود</b>")
        for i, (uid, val) in enumerate(top_profit):
            mark = medals[i] if i < len(medals) else f"{i + 1}."
            lines.append(f"{mark} {_name(uid)} — {val:,} واحد")

    if sessions:
        max_bet = max(s["bet"] for s in sessions.values())
        top_sessions = [s for s in sessions.values() if s["bet"] == max_bet]
        lines.append("")
        lines.append(f"<b>💎 بیشترین شرط · یک بازی{_plabel(prize_max_bet)}</b>")
        lines.append(f"💰 مبلغ ورودی: {max_bet:,} واحد")
        shown = 0
        for sess in top_sessions:
            players = sorted(sess["players"], key=str)
            names = [_name(p) for p in players]
            if len(names) == 2:
                lines.append(f"👥 {' × '.join(names)}")
            elif names:
                lines.append(f"👥 {' · '.join(names)}")
            shown += 1
            if shown >= MAX_BET_GAMES:
                break
        extra = len(top_sessions) - shown
        if extra > 0:
            lines.append(f"… و {extra} بازی دیگر با همین مبلغ")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_my_dice_stats(records, title: str, user_label: str) -> str:
    """آمار شخصی یک بازیکن — HTML."""
    if not records:
        return f"<b>{title}</b>\n\n📭 در این بازه مسابقه‌ای برای شما ثبت نشده."

    games = len(records)
    wins = sum(1 for r in records if r.winner)
    ties = sum(
        1
        for r in records
        if not r.winner and int(r.amount_won or 0) == 0 and int(r.bet_amount or 0) > 0
    )
    losses = max(0, games - wins - ties)
    max_bet = max((int(r.bet_amount or 0) for r in records), default=0)

    if wins >= losses:
        status = "🟢"
    else:
        status = "🔴"

    lines = [
        f"<b>{title}</b>",
        f"👤 {user_label}",
        "━━━━━━━━━━━━━━━━",
        f"🎮 تعداد بازی: {games}",
        f"🏆 برد: {wins}",
        f"💔 باخت: {losses}",
    ]
    if ties:
        lines.append(f"🤝 تساوی: {ties}")
    lines.append(f"📊 وضعیت: {status}")
    if max_bet > 0:
        lines.append(f"💎 بیشترین مبلغ شرط: {max_bet:,} واحد")
    lines.append("━━━━━━━━━━━━━━━━")
    return "\n".join(lines)
