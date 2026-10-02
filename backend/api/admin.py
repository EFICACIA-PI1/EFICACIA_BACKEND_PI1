from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import Event, Organizer, Profile, Task


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0


class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Organizer)
class OrganizerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "last_name", "daily_hours_limit", "user_type")
    search_fields = ("name", "last_name")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "event_type", "event_date", "user", "organizer")
    list_filter = ("event_type",)
    search_fields = ("name", "client_contact")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "type", "state", "due_date", "estimated_hours", "event", "parent")
    list_filter = ("type", "state")
    search_fields = ("name",)
