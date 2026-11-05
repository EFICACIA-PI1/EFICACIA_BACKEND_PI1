from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.authtoken.models import Token

from api.models import Event, Task

User = get_user_model()


def event_payload(name="Nuevo evento"):
    return {
        "name": name,
        "event_type": "social",
        "client_contact": "3001112233",
        "event_date": "2030-05-10T18:00:00-05:00",
        "location": "Bogotá",
    }


def task_payload(name="Nueva gestión", due_date=None, **extra):
    payload = {
        "name": name,
        "description": "Descripción",
        "due_date": due_date or str(date.today() + timedelta(days=2)),
        "estimated_hours": "1.50",
        "note": "",
        "state": "pendiente",
        "type": "task",
    }
    payload.update(extra)
    return payload


def test_health_and_authentication(api_client):
    assert api_client.get("/api/health/").status_code == 200
    assert api_client.get("/api/events/").status_code == 401


def test_register_and_login(api_client, db):
    response = api_client.post(
        "/api/auth/register/",
        {
            "username": "registro",
            "email": "registro@example.com",
            "password": "ClaveSegura123",
            "password_confirm": "ClaveSegura123",
            "full_name": "Persona Registrada",
            "phone": "3001234567",
        },
        format="json",
    )

    assert response.status_code == 201
    assert "token" in response.data
    login = api_client.post(
        "/api/auth/login/",
        {"username": "registro", "password": "ClaveSegura123"},
        format="json",
    )
    assert login.status_code == 200
    assert login.data["token"] == response.data["token"]


def test_login_rejects_bad_credentials(api_client, user):
    response = api_client.post(
        "/api/auth/login/",
        {"username": user.username, "password": "incorrecta"},
        format="json",
    )

    assert response.status_code == 400


def test_event_and_task_crud(authenticated_client, event):
    created_event = authenticated_client.post(
        "/api/events/", event_payload(), format="json"
    )
    assert created_event.status_code == 201
    event_id = created_event.data["id"]

    created_task = authenticated_client.post(
        f"/api/events/{event_id}/tasks/",
        task_payload(),
        format="json",
    )
    assert created_task.status_code == 201
    task_id = created_task.data["id"]
    assert authenticated_client.get(f"/api/events/{event_id}/").status_code == 200
    assert authenticated_client.patch(
        f"/api/tasks/{task_id}/", {"state": "hecha"}, format="json"
    ).status_code == 200
    assert authenticated_client.delete(f"/api/tasks/{task_id}/").status_code == 204


def test_profile_change_password_and_logout(authenticated_client, user):
    profile = authenticated_client.get("/api/auth/me/")
    assert profile.status_code == 200
    updated = authenticated_client.patch(
        "/api/auth/me/",
        {"full_name": "Nombre Editado", "address": "Cali"},
        format="json",
    )
    assert updated.status_code == 200

    changed = authenticated_client.post(
        "/api/auth/change-password/",
        {
            "old_password": "ClaveSegura123",
            "new_password": "NuevaClave123",
            "new_password_confirm": "NuevaClave123",
        },
        format="json",
    )
    assert changed.status_code == 200
    assert authenticated_client.post("/api/auth/logout/").status_code == 204


def test_password_reset_flow(api_client, user):
    requested = api_client.post(
        "/api/auth/password-reset/",
        {"email": user.email},
        format="json",
    )
    assert requested.status_code == 200
    assert len(mail.outbox) == 1

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    confirmed = api_client.post(
        "/api/auth/password-reset/confirm/",
        {
            "uid": uid,
            "token": token,
            "new_password": "NuevaClave123",
            "new_password_confirm": "NuevaClave123",
        },
        format="json",
    )
    assert confirmed.status_code == 200
    assert User.objects.get(pk=user.pk).check_password("NuevaClave123")


def test_progress_and_today_filters(authenticated_client, event):
    today = date.today()
    Task.objects.create(
        event=event,
        name="Vencida",
        due_date=today - timedelta(days=1),
        estimated_hours=Decimal("1.00"),
    )
    Task.objects.create(
        event=event,
        name="Hoy",
        due_date=today,
        estimated_hours=Decimal("2.00"),
    )
    Task.objects.create(
        event=event,
        name="Próxima",
        due_date=today + timedelta(days=1),
        estimated_hours=Decimal("3.00"),
    )

    today_response = authenticated_client.get("/api/hoy/")
    progress = authenticated_client.get("/api/events/progress/")

    assert today_response.status_code == 200
    assert [t["name"] for t in today_response.data["para_hoy"]] == ["Hoy"]
    assert progress.data == {"hechas": 0, "total": 3, "porcentaje": 0}
    assert authenticated_client.get("/api/hoy/?state=invalid").status_code == 400


def test_daily_overload_returns_structured_conflict(
    authenticated_client, event, task, user
):
    user.profile.daily_hours_limit = 2
    user.profile.save(update_fields=["daily_hours_limit"])
    response = authenticated_client.patch(
        f"/api/tasks/{task.pk}/",
        {
            "due_date": str(task.due_date + timedelta(days=1)),
            "estimated_hours": "3.00",
        },
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "daily_overload"
    assert response.data["limit_hours"] == 2.0


def test_user_cannot_access_another_users_event(authenticated_client, second_user):
    other_event = Event.objects.create(
        user=second_user,
        name="Privado",
        event_type="otro",
        client_contact="3000000000",
        event_date="2030-05-10T18:00:00-05:00",
        location="Cali",
    )

    response = authenticated_client.get(f"/api/events/{other_event.pk}/")

    assert response.status_code == 404
