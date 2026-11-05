from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from api.models import Event, Task
from api.serializers import (
    ChangePasswordSerializer,
    EventSerializer,
    MeSerializer,
    RegisterSerializer,
    TaskSerializer,
)

User = get_user_model()


def register_data(**overrides):
    data = {
        "username": "nueva",
        "email": "NUEVA@example.com",
        "password": "ClaveSegura123",
        "password_confirm": "ClaveSegura123",
        "full_name": "Nueva Persona",
        "phone": "+573001234567",
    }
    data.update(overrides)
    return data


def test_register_serializer_normalizes_and_validates_fields(db):
    serializer = RegisterSerializer(data=register_data())

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["email"] == "nueva@example.com"
    assert serializer.validated_data["username"] == "nueva"


@pytest.mark.parametrize(
    "field,value",
    [
        ("full_name", "x"),
        ("phone", "abc"),
        ("email", "not-an-email"),
    ],
)
def test_register_serializer_rejects_invalid_fields(db, field, value):
    serializer = RegisterSerializer(data=register_data(**{field: value}))

    assert not serializer.is_valid()
    assert field in serializer.errors


def test_register_serializer_rejects_duplicate_user_and_mismatched_password(db, user):
    duplicate = RegisterSerializer(data=register_data(username="OLIVIA"))
    mismatch = RegisterSerializer(
        data=register_data(password_confirm="OtraClave123")
    )

    assert not duplicate.is_valid()
    assert "username" in duplicate.errors
    assert not mismatch.is_valid()
    assert "password_confirm" in mismatch.errors


def test_event_serializer_reports_progress(event, task):
    Task.objects.create(
        event=event,
        name="Enviar invitaciones",
        due_date=task.due_date,
        estimated_hours=Decimal("1.00"),
        state=Task.State.HECHA,
    )

    data = EventSerializer(event).data

    assert data["progress"] == {"hechas": 1, "total": 2, "porcentaje": 50}


def test_event_serializer_rejects_past_date():
    serializer = EventSerializer(
        data={
            "name": "Evento",
            "event_type": Event.EventType.OTRO,
            "client_contact": "3001234567",
            "event_date": timezone.now() - timedelta(days=1),
            "location": "Cali",
        }
    )

    assert not serializer.is_valid()
    assert "event_date" in serializer.errors


def test_task_serializer_rejects_invalid_hierarchy(event, task):
    missing_parent = TaskSerializer(
        data={
            "name": "Paso",
            "due_date": date.today() + timedelta(days=1),
            "estimated_hours": "1.00",
            "type": Task.TaskType.SUBTASK,
        },
        context={"event": event},
    )
    wrong_parent = TaskSerializer(
        data={
            "name": "Otra",
            "due_date": date.today() + timedelta(days=1),
            "estimated_hours": "1.00",
            "type": Task.TaskType.TASK,
            "parent": task.pk,
        },
        context={"event": event},
    )

    assert not missing_parent.is_valid()
    assert "parent" in missing_parent.errors
    assert not wrong_parent.is_valid()
    assert "parent" in wrong_parent.errors


def test_task_serializer_marks_completed_task(event):
    serializer = TaskSerializer(
        data={
            "name": "Confirmar proveedores",
            "due_date": date.today() + timedelta(days=1),
            "estimated_hours": "1.50",
            "state": Task.State.HECHA,
        },
        context={"event": event},
    )

    assert serializer.is_valid(), serializer.errors
    created = serializer.save(event=event)

    assert created.done_at is not None


def test_me_serializer_updates_profile_and_protects_username(user):
    request = APIRequestFactory().patch("/api/auth/me/")
    serializer = MeSerializer(
        user,
        data={"full_name": "Olivia Actualizada", "phone": "3001234567"},
        partial=True,
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    serializer.save()
    user.refresh_from_db()
    assert user.profile.full_name == "Olivia Actualizada"

    protected = MeSerializer(user, data={"username": "otro"}, partial=True)
    assert not protected.is_valid()
    assert "username" in protected.errors


def test_change_password_serializer_validates_confirmation(user):
    request = APIRequestFactory().post("/api/auth/change-password/")
    request.user = user
    serializer = ChangePasswordSerializer(
        data={
            "old_password": "ClaveSegura123",
            "new_password": "NuevaClave123",
            "new_password_confirm": "Distinta123",
        },
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert "new_password_confirm" in serializer.errors
