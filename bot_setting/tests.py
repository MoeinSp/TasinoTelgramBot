from django.test import TestCase

from account.models import TelegramGroup
from bot_setting.models import ForcedJoinConfig, GroupForcedJoin
from types import SimpleNamespace
from unittest.mock import AsyncMock
from aiogram.enums import ChatMemberStatus


class GroupForcedJoinTests(TestCase):
    def setUp(self):
        self.group = TelegramGroup.objects.create(telegram_chat_id=-1001234567890, name="Test")

    def test_each_group_has_at_most_one_owner_link(self):
        GroupForcedJoin.objects.create(
            group=self.group, channel_id=-1001, title="one", invite_link="https://t.me/one",
        )
        with self.assertRaises(Exception):
            GroupForcedJoin.objects.create(
                group=self.group, channel_id=-1002, title="two", invite_link="https://t.me/two",
            )

    async def test_creator_and_owner_targets_are_combined(self):
        creator = await ForcedJoinConfig.objects.aget_or_create(pk=1)
        cfg = creator[0]
        cfg.enabled = True
        cfg.channel_id = -2001
        cfg.channel_title = "creator"
        cfg.channel_username = "creator_channel"
        await cfg.asave()
        await GroupForcedJoin.objects.acreate(
            group=self.group, channel_id=-2002, title="owner", invite_link="https://t.me/owner_channel",
        )
        from bot.group_forced_join import load_targets
        targets = await load_targets(self.group.telegram_chat_id)
        self.assertEqual({t.title for t in targets}, {"creator", "owner"})
        self.assertEqual(len(targets), 2)

    async def test_admin_is_exempt_from_creator_and_group_links(self):
        cfg, _ = await ForcedJoinConfig.objects.aget_or_create(pk=1)
        cfg.enabled = True
        cfg.channel_id = -2001
        cfg.channel_title = "creator"
        cfg.channel_username = "creator_channel"
        await cfg.asave()
        await GroupForcedJoin.objects.acreate(
            group=self.group, channel_id=-2002, title="owner", invite_link="https://t.me/owner_channel",
        )
        bot = SimpleNamespace(get_chat_member=AsyncMock(side_effect=lambda chat_id, user_id: SimpleNamespace(
            status=ChatMemberStatus.ADMINISTRATOR if chat_id == self.group.telegram_chat_id else ChatMemberStatus.LEFT
        )))
        from bot.group_forced_join import missing_targets
        applicable, missing = await missing_targets(bot, self.group.telegram_chat_id, 123)
        self.assertEqual(applicable, [])
        self.assertEqual(missing, [])

# Create your tests here.
