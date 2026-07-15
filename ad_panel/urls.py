from django.urls import path
from . import views

app_name = "ad_panel"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("slot/", views.post_slot, name="post_slot"),
    path("custom/", views.post_custom, name="post_custom"),
    path("periodic/", views.post_periodic, name="post_periodic"),
    path("post/", views.post_ad, name="post"),
    path("campaign/", views.post_ad, name="campaign"),
    path("join/", views.join_page, name="join"),
    path("schedules/", views.schedules, name="schedules"),
    path("schedules/new/", views.schedule_edit, name="schedule_new"),
    path("schedules/<int:pk>/", views.schedule_edit, name="schedule_edit"),
    path("schedules/<int:pk>/delete/", views.schedule_delete, name="schedule_delete"),
    path("loadouts/", views.schedules, name="loadouts"),
    path("loadouts/new/", views.schedule_edit, name="loadout_new"),
    path("loadouts/<int:pk>/", views.schedule_edit, name="loadout_edit"),
    path("loadouts/<int:pk>/delete/", views.schedule_delete, name="loadout_delete"),
    path("ad/<int:pk>/toggle/", views.toggle_ad, name="toggle_ad"),
    path("ad/<int:pk>/delete/", views.delete_ad, name="delete_ad"),
    path("join/<int:pk>/off/", views.deactivate_join, name="deactivate_join"),
    path("join/<int:pk>/priority/", views.join_set_priority, name="join_set_priority"),
    path("join/renumber/", views.join_renumber, name="join_renumber"),
    path("clear-today/", views.clear_today, name="clear_today"),
    path("stats/", views.stats_page, name="stats"),
    path("tools/", views.tools_page, name="tools"),
]
