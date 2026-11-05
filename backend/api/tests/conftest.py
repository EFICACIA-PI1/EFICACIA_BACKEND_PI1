from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import Event, Organizer, Task

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="olivia",
        email="olivia@example.com",
        password="ClaveSegura123",
    )


@pytest.fixture
def second_user(db):
    return User.objects.create_user(
        username="marco",
        email="marco@example.com",
        password="ClaveSegura123",
    )


@pytest.fixture
def authenticated_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def event(user):
    return Event.objects.create(
        user=user,
        name="Boda familiar",
        event_type=Event.EventType.BODA,
        client_contact="3001234567",
        event_date=timezone.make_aware(
            datetime.combine(date.today() + timedelta(days=10), time(18))
        ),
        location="Cali",
    )


@pytest.fixture
def task(event):
    return Task.objects.create(
        event=event,
        name="Reservar salón",
        due_date=date.today() + timedelta(days=3),
        estimated_hours=Decimal("2.00"),
    )


@pytest.fixture
def organizer(db):
    return Organizer.objects.create(name="Ana", last_name="Gómez")
