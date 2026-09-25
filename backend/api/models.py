from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class Organizer(models.Model):
    """Organizador de eventos. Sprint 1 usa un organizador demo (sin login)."""

    name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    daily_hours_limit = models.PositiveSmallIntegerField(
        default=6,
        validators=[MinValueValidator(1), MaxValueValidator(16)],
    )
    user_type = models.CharField(max_length=50, default="organizador")

    class Meta:
        db_table = "api_organizer"

    def __str__(self):
        return f"{self.name} {self.last_name}"


class Event(models.Model):
    class EventType(models.TextChoices):
        BODA = "boda", "Boda"
        SOCIAL = "social", "Social"
        CORPORATIVO = "corporativo", "Corporativo"
        CUMPLEANOS = "cumpleanos", "Cumpleaños"
        OTRO = "otro", "Otro"

    organizer = models.ForeignKey(Organizer, on_delete=models.CASCADE, related_name="events")
    name = models.CharField(max_length=150)
    event_type = models.CharField(max_length=30, choices=EventType.choices, default=EventType.OTRO)
    client_contact = models.CharField(max_length=150)
    event_date = models.DateTimeField()
    location = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "api_event"
        ordering = ["-event_date"]

    def __str__(self):
        return self.name


class Task(models.Model):
    """Gestión logística de un evento (type=task) o paso dentro de ella (type=subtask).

    Una fila type=subtask usa `parent` (columna group_id) para apuntar a la
    tarea padre; una fila type=task no tiene padre (es la gestión de nivel
    superior asociada directamente al evento, p. ej. "Reservar salón").
    """

    class TaskType(models.TextChoices):
        TASK = "task", "Tarea"
        SUBTASK = "subtask", "Subtarea"

    class State(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        HECHA = "hecha", "Hecha"
        POSPUESTA = "pospuesta", "Pospuesta"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="tasks")
    organizer = models.ForeignKey(Organizer, on_delete=models.CASCADE, related_name="tasks")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subtasks",
        db_column="group_id",
    )
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=500, blank=True, default="")
    due_date = models.DateField()
    estimated_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.1"))],
    )
    state = models.CharField(max_length=20, choices=State.choices, default=State.PENDIENTE)
    type = models.CharField(max_length=20, choices=TaskType.choices, default=TaskType.TASK)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "api_task"
        ordering = ["due_date"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(type="task", parent__isnull=True)
                    | models.Q(type="subtask", parent__isnull=False)
                ),
                name="task_type_parent_consistency",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.parent_id and self.parent.type != self.TaskType.TASK:
            raise ValidationError(
                {"parent": "La tarea padre debe ser una tarea de nivel superior, no otra subtarea."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
