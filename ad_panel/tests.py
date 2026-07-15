from django.test import TestCase

from scheduledmessage.models import ScheduledMessage

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
