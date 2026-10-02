from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from api.demo import get_demo_organizer
from api.models import Event, Task

User = get_user_model()


class Command(BaseCommand):
    help = "Crea datos demo minimos: usuario, un evento y su plan inicial de subtareas."

    def handle(self, *args, **options):
        organizer = get_demo_organizer()
        if organizer.user_id is None:
            user, created = User.objects.get_or_create(
                username="demo",
                defaults={"email": "demo@eficacia.local"},
            )
            if created or not user.has_usable_password():
                user.set_password("demo123")
                user.save()
            organizer.user = user
            organizer.save(update_fields=["user"])

        event, event_created = Event.objects.get_or_create(
            user=organizer.user,
            organizer=organizer,
            name="Boda de Ana y Luis",
            defaults={
                "event_type": Event.EventType.BODA,
                "client_contact": "Ana Martínez - 3001234567",
                "event_date": "2026-12-15T18:00:00Z",
                "location": "Salón Los Almendros",
            },
        )
        if not event_created:
            self.stdout.write("El evento demo ya existía, no se duplicó.")

        subtareas = [
            {"name": "Reservar salón", "due_date": "2026-11-01", "estimated_hours": "3"},
            {"name": "Enviar invitaciones", "due_date": "2026-11-10", "estimated_hours": "4"},
            {"name": "Confirmar catering", "due_date": "2026-11-20", "estimated_hours": "2"},
        ]
        for data in subtareas:
            Task.objects.get_or_create(
                event=event,
                organizer=organizer,
                name=data["name"],
                defaults={
                    "due_date": data["due_date"],
                    "estimated_hours": data["estimated_hours"],
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo: usuario demo (id={organizer.user_id}), "
                f"evento '{event.name}' (id={event.id}) con {event.tasks.count()} tareas."
            )
        )
