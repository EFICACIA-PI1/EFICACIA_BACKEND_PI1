from django.contrib import admin

from .models import Event, Organizer, Task


@admin.register(Organizer)
class OrganizerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "last_name", "daily_hours_limit", "user_type")
    search_fields = ("name", "last_name")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "event_type", "event_date", "organizer")
    list_filter = ("event_type",)
    search_fields = ("name", "client_contact")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "type", "state", "due_date", "estimated_hours", "event", "parent")
    list_filter = ("type", "state")
    search_fields = ("name",)
