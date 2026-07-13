"""Repair DB after partial restore without dropping the database."""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


# (app, migration_name, table, column) — fake if column exists but migration not recorded
COLUMN_MIGRATIONS = [
    ("account", "0010_telegramgroup_dice_turn_limit", "account_telegramgroup", "dice_turn_limit"),
    ("account", "0011_telegramgroupmember_balance_hidden", "account_telegramgroupmember", "balance_hidden"),
    ("account", "0012_telegramgroupmember_accounts_hidden", "account_telegramgroupmember", "accounts_hidden"),
    ("account", "0013_telegramgroup_bet_mode", "account_telegramgroup", "bet_mode"),
    ("account", "0014_telegramgroup_increase_hidden", "account_telegramgroup", "increase_hidden"),
    ("bot_setting", "0004_botsiteconfig_premium_emoji_ids", "bot_setting_botsiteconfig", "premium_emoji_ids"),
    ("bot_setting", "0005_botsiteconfig_dice_themes", "bot_setting_botsiteconfig", "dice_themes"),
    ("bot_setting", "0006_botsiteconfig_bot_enabled", "bot_setting_botsiteconfig", "bot_enabled"),
    ("bot_setting", "0007_databasebackuptool", "bot_setting_databasebackuptool", "id"),
]


def column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        LIMIT 1
        """,
        [table, column],
    )
    return cursor.fetchone() is not None


def table_exists(cursor, table: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        LIMIT 1
        """,
        [table],
    )
    return cursor.fetchone() is not None


def migration_applied(cursor, app: str, name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM django_migrations WHERE app = %s AND name = %s LIMIT 1",
        [app, name],
    )
    return cursor.fetchone() is not None


def fk_exists(cursor, constraint_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM pg_constraint WHERE conname = %s LIMIT 1",
        [constraint_name],
    )
    return cursor.fetchone() is not None


class Command(BaseCommand):
    help = "Fix orphaned rows and sync django_migrations with existing schema (no data wipe)."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM account_telegramgroupmember m
                WHERE NOT EXISTS (
                    SELECT 1 FROM account_telegramgroup g WHERE g.id = m.group_id
                )
                """
            )
            orphans = cursor.rowcount
            self.stdout.write(f"Removed {orphans} orphan telegramgroupmember row(s)")

            if not fk_exists(cursor, "account_telegramgroupmember_group_id_c2165180_fk"):
                orphan_check = """
                    SELECT COUNT(*) FROM account_telegramgroupmember m
                    WHERE NOT EXISTS (
                        SELECT 1 FROM account_telegramgroup g WHERE g.id = m.group_id
                    )
                """
                cursor.execute(orphan_check)
                if cursor.fetchone()[0] == 0:
                    cursor.execute(
                        """
                        ALTER TABLE account_telegramgroupmember
                        ADD CONSTRAINT account_telegramgroupmember_group_id_c2165180_fk
                        FOREIGN KEY (group_id) REFERENCES account_telegramgroup(id)
                        DEFERRABLE INITIALLY DEFERRED
                        """
                    )
                    self.stdout.write("Added missing FK on telegramgroupmember.group_id")
                else:
                    self.stdout.write(self.style.WARNING("FK still missing; orphan rows remain"))

            for app, migration, table, column in COLUMN_MIGRATIONS:
                if migration_applied(cursor, app, migration):
                    continue
                exists = table_exists(cursor, table) and (
                    column_exists(cursor, table, column)
                    if column != "id"
                    else True
                )
                if exists:
                    call_command("migrate", app, migration, fake=True, verbosity=1)
                    self.stdout.write(f"Faked {app}.{migration} (schema already present)")

        self.stdout.write("Running migrate...")
        call_command("migrate", "--no-input", verbosity=1)
        self.stdout.write(self.style.SUCCESS("repair_db done"))
