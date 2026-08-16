from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from scheduledmessage.models import ScheduledMessage
from bot_setting.models import JoinMessage

from .forms import PeriodicAdForm
from .services import (
    apply_periodic_ad, cleanup_preview, cleanup_run, list_periodic_ads,
    parse_time, slot_to_run_at, today_local,
)


class PeriodicAdTests(TestCase):
    def test_creates_scheduler_interval_record(self):
        ad = apply_periodic_ad(mode="bomb", text="test ad", interval_minutes=60)

        self.assertEqual(ad.type, "interval")
        self.assertEqual(ad.interval_minutes, 60)
        self.assertTrue(ad.send_to_all)
        self.assertTrue(ad.send_to_pv)
        self.assertTrue(ad.is_active)
        self.assertIsNone(ad.run_at)
        self.assertEqual(list(list_periodic_ads()), [ad])

    def test_form_rejects_invalid_interval(self):
        form = PeriodicAdForm({"mode": "group", "text": "ad", "interval_minutes": 0})
        self.assertFalse(form.is_valid())
        self.assertIn("interval_minutes", form.errors)

    def test_service_rejects_invalid_mode(self):
        with self.assertRaises(ValueError):
            apply_periodic_ad(mode="invalid", text="ad", interval_minutes=10)
        self.assertFalse(ScheduledMessage.objects.exists())

    def test_extended_hour_27_is_tomorrow_at_three(self):
        slot = parse_time("27")
        run_at = slot_to_run_at(today_local(), slot, day_mode="today")
        self.assertEqual(slot, "27:00")
        self.assertEqual(run_at.date(), today_local() + __import__("datetime").timedelta(days=1))
        self.assertEqual((run_at.hour, run_at.minute), (3, 0))

    def test_cleanup_counts_and_deletes_inactive_periodic_ads(self):
        ad = apply_periodic_ad(mode="group", text="old", interval_minutes=10)
        ad.is_active = False
        ad.save(update_fields=["is_active"])
        self.assertEqual(cleanup_preview()["inactive"], 1)
        self.assertEqual(cleanup_run("inactive_ads")["deleted_ads"], 1)
        self.assertFalse(ScheduledMessage.objects.filter(pk=ad.pk).exists())

    def test_join_window_now_until_tomorrow_same_time(self):
        from .services import JOIN_WINDOW_NOW_24H, join_window_for

        start, end = join_window_for(JOIN_WINDOW_NOW_24H)
        self.assertEqual(end - start, timedelta(days=1))
        self.assertLessEqual(abs((start - timezone.localtime()).total_seconds()), 60)

    def test_join_window_noon_tomorrow(self):
        from .services import JOIN_WINDOW_NOON_TOMORROW, join_window_for

        start, end = join_window_for(JOIN_WINDOW_NOON_TOMORROW)
        self.assertEqual((start.hour, start.minute), (12, 0))
        self.assertEqual(start.date(), today_local() + timedelta(days=1))
        self.assertEqual(end - start, timedelta(days=1))

    def test_super_ad_without_join_keeps_existing_join(self):
        from .services import apply_join_only, apply_single_ad

        apply_join_only(["https://keep.example"])
        apply_single_ad(mode="super", slot="20:00", text="ad text", join_links=[])
        self.assertEqual(JoinMessage.objects.filter(is_active=True).count(), 1)
        self.assertEqual(JoinMessage.objects.get().text, "https://keep.example")

    def test_expired_campaign_join_is_not_shown_in_panel(self):
        from .services import current_join_prefill, expire_stale_joins, latest_campaign_join

        now = timezone.now()
        JoinMessage.objects.create(
            title="[JOIN] stale",
            text="https://yesterday.example",
            is_active=True,
            is_forever=False,
            priority=1,
            start_datetime=now - timedelta(days=2),
            end_datetime=now - timedelta(hours=1),
        )
        self.assertIsNone(latest_campaign_join())
        self.assertEqual(current_join_prefill()["join_link"], "")
        self.assertEqual(expire_stale_joins(), 0)
        self.assertFalse(JoinMessage.objects.get().is_active)

    def test_super_ad_with_join_replaces_previous_campaign_join(self):
        from .services import (
            JOIN_WINDOW_NOON_TODAY, apply_join_only, apply_single_ad, latest_campaign_join,
        )

        apply_join_only(["https://old.example"])
        apply_single_ad(
            mode="super", slot="12:00", text="noon ad",
            join_links=["https://new.example"], join_window=JOIN_WINDOW_NOON_TODAY,
        )
        self.assertFalse(
            JoinMessage.objects.filter(is_active=True, text="https://old.example").exists()
        )
        newest = latest_campaign_join()
        self.assertIsNotNone(newest)
        self.assertEqual(newest.text, "https://new.example")

    def test_future_campaign_join_shows_in_header_but_does_not_prefill(self):
        from .services import (
            JOIN_WINDOW_FOREVER, JOIN_WINDOW_NOON_TOMORROW, apply_join_only,
            apply_single_ad, current_join_prefill, latest_campaign_join,
        )

        apply_join_only(["@Tasino_ir"], window_kind=JOIN_WINDOW_FOREVER)
        apply_join_only(["https://old.example"])
        apply_single_ad(
            mode="super", slot="12:00", text="noon ad",
            join_links=["https://new.example"], join_window=JOIN_WINDOW_NOON_TOMORROW,
        )
        self.assertTrue(
            JoinMessage.objects.filter(text="@Tasino_ir", is_active=True, is_forever=True).exists()
        )
        self.assertFalse(
            JoinMessage.objects.filter(is_active=True, text="https://old.example").exists()
        )
        self.assertEqual(latest_campaign_join().text, "https://new.example")
        self.assertEqual(current_join_prefill()["join_link"], "")

    def test_duplicate_join_refreshes_window(self):
        from .services import JOIN_WINDOW_NOON_TODAY, JOIN_WINDOW_NOW_24H, apply_join_only

        apply_join_only(["https://same.example"], window_kind=JOIN_WINDOW_NOON_TODAY)
        second = apply_join_only(["https://same.example"], window_kind=JOIN_WINDOW_NOW_24H)
        obj = JoinMessage.objects.get()
        self.assertEqual(JoinMessage.objects.count(), 1)
        self.assertEqual(
            timezone.localtime(obj.start_datetime).replace(second=0, microsecond=0),
            timezone.localtime(second["start"]).replace(second=0, microsecond=0),
        )
