from django import forms
from .models import AdLoadout
from .services import parse_time, parse_entries


MODE_CHOICES = AdLoadout.MODE_CHOICES


class ScheduleForm(forms.ModelForm):
    class Meta:
        model = AdLoadout
        fields = ("name", "is_favorite")
        labels = {
            "name": "نام برنامه",
            "is_favorite": "استفاده در پنل امروز",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_favorite"].required = False

    def save_with_entries(self, entries: list[dict], commit=True):
        obj = super().save(commit=False)
        obj.slots = parse_entries(entries)
        if commit:
            obj.save()
        return obj


# سازگاری
LoadoutForm = ScheduleForm


class SlotPostForm(forms.Form):
    time = forms.CharField()
    mode = forms.ChoiceField(choices=MODE_CHOICES)
    text = forms.CharField(required=False, widget=forms.Textarea)
    join_link = forms.CharField(required=False)
    day_mode = forms.ChoiceField(
        choices=(
            ("auto", "خودکار"),
            ("today", "امروز"),
            ("tomorrow_am", "بامداد فردا"),
        ),
        required=False,
        initial="auto",
    )

    def clean_time(self):
        t = parse_time(self.cleaned_data["time"])
        if not t:
            raise forms.ValidationError("ساعت نامعتبر")
        return t

    def clean_text(self):
        return (self.cleaned_data.get("text") or "").strip()

    def clean_day_mode(self):
        v = self.cleaned_data.get("day_mode") or "auto"
        return v if v in ("auto", "today", "tomorrow_am") else "auto"

    def clean(self):
        cleaned = super().clean()
        link = (cleaned.get("join_link") or "").strip()
        cleaned["join_links"] = [link] if link else []
        return cleaned


class CustomAdForm(forms.Form):
    schedule_type = forms.ChoiceField(
        label="نوع زمان‌بندی",
        choices=(("fixed", "یک‌باره در ساعت مشخص"), ("interval", "دوره‌ای")),
        initial="fixed",
    )
    time = forms.CharField(
        required=False,
        label="ساعت",
        widget=forms.TextInput(attrs={"placeholder": "25:00 یا 09:00", "dir": "ltr", "class": "slots-input"}),
    )
    day_mode = forms.ChoiceField(
        label="روز ارسال",
        choices=(
            ("auto", "خودکار (۲۵ یا قبل ۶صبح = بامداد فردا)"),
            ("today", "همین امروز"),
            ("tomorrow_am", "بامداد فردا — ثبت از امروز"),
        ),
        initial="auto",
    )
    mode = forms.ChoiceField(choices=MODE_CHOICES, initial="bomb", label="نوع")
    text = forms.CharField(
        required=False,
        label="متن",
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "متن تبلیغ… (خالی = بدون تبلیغ این ساعت)",
        }),
    )
    join_link = forms.CharField(
        required=False,
        label="لینک جوین",
        widget=forms.TextInput(attrs={"placeholder": "فقط سوپر بمب", "dir": "ltr"}),
    )
    interval_minutes = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10080,
        label="فاصله ارسال (دقیقه)",
    )

    def clean_time(self):
        if self.cleaned_data.get("schedule_type") == "interval":
            return ""
        t = parse_time(self.cleaned_data.get("time"))
        if not t:
            raise forms.ValidationError("ساعت نامعتبر (۰۰–۲۳ یا ۲۵:۰۰)")
        return t

    def clean_text(self):
        return (self.cleaned_data.get("text") or "").strip()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("schedule_type") == "interval" and not cleaned.get("interval_minutes"):
            self.add_error("interval_minutes", "فاصله ارسال برای تبلیغ دوره‌ای لازم است.")
        link = (cleaned.get("join_link") or "").strip()
        cleaned["join_links"] = [link] if link else []
        # سوپر بمب فقط وقتی متن دارد لینک لازم است
        if cleaned.get("mode") == "super" and cleaned.get("text") and not link:
            raise forms.ValidationError("برای سوپر بمب لینک جوین لازم است.")
        return cleaned


class PeriodicAdForm(forms.Form):
    mode = forms.ChoiceField(choices=MODE_CHOICES, initial="group", label="نوع")
    interval_minutes = forms.IntegerField(
        min_value=1,
        max_value=10080,
        label="فاصله ارسال (دقیقه)",
        widget=forms.NumberInput(attrs={"min": 1, "max": 10080, "placeholder": "مثلاً 60"}),
    )
    text = forms.CharField(
        label="متن",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "متن تبلیغ دوره‌ای…"}),
    )

    def clean_text(self):
        return (self.cleaned_data.get("text") or "").strip()


class JoinOnlyForm(forms.Form):
    join_links = forms.CharField(
        label="لینک‌ها (تا ۵ تا)",
        widget=forms.Textarea(attrs={
            "rows": 6,
            "placeholder": "هر خط یک لینک (اولویت به ترتیب ۱،۲،۳…)\nیا با اولویت صریح:\n1|https://...\n2|https://...",
            "dir": "ltr",
        }),
    )

    def clean_join_links(self):
        links = []
        for line in self.cleaned_data["join_links"].splitlines():
            line = line.strip()
            if line:
                links.append(line)
        if not links:
            raise forms.ValidationError("حداقل یک لینک لازم است.")
        return links[:5]


# سازگاری قدیمی
class PostAdForm(forms.Form):
    MODE_CHOICES = MODE_CHOICES
    schedule = forms.ModelChoiceField(queryset=AdLoadout.objects.all(), required=False)
    mode = forms.ChoiceField(choices=MODE_CHOICES, initial="bomb")
    slots = forms.CharField(required=False)
    text = forms.CharField(widget=forms.Textarea)
    join_links = forms.CharField(required=False)


QuickCampaignForm = PostAdForm
