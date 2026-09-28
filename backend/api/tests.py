from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .demo import get_demo_organizer
from .models import Event, Organizer, Task

User = get_user_model()


def make_event(**overrides):
    data = {
        "organizer": get_demo_organizer(),
        "name": "Evento de prueba",
        "event_type": Event.EventType.OTRO,
        "client_contact": "Contacto",
        "event_date": "2026-12-01T18:00:00Z",
        "location": "Lugar de prueba",
    }
    data.update(overrides)
    return Event.objects.create(**data)


def make_organizer_user(username, password="clave123", **organizer_fields):
    user = User.objects.create_user(username=username, password=password)
    fields = {
        "user": user,
        "name": username.capitalize(),
        "last_name": "Organizador",
        "user_type": "organizador",
    }
    fields.update(organizer_fields)
    organizer = Organizer.objects.create(**fields)
    token = Token.objects.create(user=user)
    return user, organizer, token


class AuthenticatedAPITestCase(APITestCase):
    """Los tests de Sprint 1 siguen usando el organizador demo, ahora con token."""

    def setUp(self):
        self.user = User.objects.create_user(username="demo", password="demo123")
        self.organizer = get_demo_organizer()
        self.organizer.user = self.user
        self.organizer.save(update_fields=["user"])
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")


class EventAPITests(AuthenticatedAPITestCase):
    """US-01: crear/ver evento. US-03: editar/eliminar evento."""

    def test_create_event_valid(self):
        url = reverse("event-list-create")
        payload = {
            "name": "Boda de Ana",
            "event_type": "boda",
            "client_contact": "Ana",
            "event_date": "2026-12-01T18:00:00Z",
            "location": "Salón X",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Event.objects.count(), 1)

    def test_create_event_missing_name_is_rejected(self):
        url = reverse("event-list-create")
        payload = {
            "name": "",
            "event_type": "boda",
            "client_contact": "Ana",
            "event_date": "2026-12-01T18:00:00Z",
            "location": "Salón X",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)
        self.assertEqual(Event.objects.count(), 0)

    def test_retrieve_event_includes_nested_tasks(self):
        event = make_event()
        Task.objects.create(
            event=event, organizer=event.organizer, name="Reservar salón",
            due_date="2026-11-01", estimated_hours=3,
        )
        url = reverse("event-detail", args=[event.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["tasks"]), 1)

    def test_update_event(self):
        event = make_event()
        url = reverse("event-detail", args=[event.id])
        response = self.client.patch(url, {"location": "Salón nuevo"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.location, "Salón nuevo")

    def test_delete_event_then_404(self):
        event = make_event()
        url = reverse("event-detail", args=[event.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], "Evento no encontrado.")


class TaskAPITests(AuthenticatedAPITestCase):
    """US-02: crear plan inicial de subtareas. US-03: editar/eliminar subtarea."""

    def setUp(self):
        super().setUp()
        self.event = make_event()
        self.list_url = reverse("task-list-create", args=[self.event.id])

    def test_create_task_valid_defaults_to_task_pendiente(self):
        payload = {"name": "Reservar salón", "due_date": "2026-11-01", "estimated_hours": 4}
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["type"], "task")
        self.assertEqual(response.data["state"], "pendiente")
        self.assertIsNone(response.data["parent"])

    def test_create_task_missing_name_is_rejected(self):
        payload = {"name": "", "due_date": "2026-11-01", "estimated_hours": 4}
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_create_task_zero_hours_is_rejected(self):
        payload = {"name": "Enviar invitaciones", "due_date": "2026-11-01", "estimated_hours": 0}
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estimated_hours", response.data)

    def test_create_task_for_nonexistent_event_is_404(self):
        url = reverse("task-list-create", args=[99999])
        response = self.client.post(url, {"name": "X", "due_date": "2026-11-01", "estimated_hours": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], "Evento no encontrado.")

    def test_create_subtask_requires_parent(self):
        payload = {"name": "Llamar proveedor", "due_date": "2026-11-01", "estimated_hours": 1, "type": "subtask"}
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("parent", response.data)

    def test_create_task_type_cannot_have_parent(self):
        parent = Task.objects.create(
            event=self.event, organizer=self.event.organizer, name="Tarea padre",
            due_date="2026-11-01", estimated_hours=2,
        )
        payload = {
            "name": "Otra tarea", "due_date": "2026-11-01", "estimated_hours": 1,
            "parent": parent.id,
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("parent", response.data)

    def test_create_subtask_valid(self):
        parent = Task.objects.create(
            event=self.event, organizer=self.event.organizer, name="Tarea padre",
            due_date="2026-11-01", estimated_hours=2,
        )
        payload = {
            "name": "Llamar proveedor", "due_date": "2026-10-28", "estimated_hours": 1,
            "type": "subtask", "parent": parent.id,
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_subtask_parent_from_other_event_is_rejected(self):
        other_event = make_event(name="Otro evento")
        other_task = Task.objects.create(
            event=other_event, organizer=other_event.organizer, name="Tarea de otro evento",
            due_date="2026-11-01", estimated_hours=1,
        )
        payload = {
            "name": "Sub", "due_date": "2026-11-01", "estimated_hours": 1,
            "type": "subtask", "parent": other_task.id,
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("parent", response.data)

    def test_subtask_of_subtask_is_rejected(self):
        parent = Task.objects.create(
            event=self.event, organizer=self.event.organizer, name="Tarea padre",
            due_date="2026-11-01", estimated_hours=2,
        )
        subtask = Task.objects.create(
            event=self.event, organizer=self.event.organizer, name="Subtarea",
            due_date="2026-11-01", estimated_hours=1, type=Task.TaskType.SUBTASK, parent=parent,
        )
        payload = {
            "name": "Sub de sub", "due_date": "2026-11-01", "estimated_hours": 1,
            "type": "subtask", "parent": subtask.id,
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("parent", response.data)

    def test_update_and_delete_task(self):
        task = Task.objects.create(
            event=self.event, organizer=self.event.organizer, name="Reservar salón",
            due_date="2026-11-01", estimated_hours=3,
        )
        detail_url = reverse("task-detail", args=[task.id])

        response = self.client.patch(detail_url, {"estimated_hours": 5}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], "Tarea no encontrada.")


class TaskModelConstraintTests(APITestCase):
    """Refuerzo del invariante type/parent a nivel de modelo y BD (no solo API)."""

    def test_full_clean_rejects_task_type_with_parent(self):
        event = make_event()
        parent = Task.objects.create(
            event=event, organizer=event.organizer, name="Padre",
            due_date="2026-11-01", estimated_hours=2,
        )
        with self.assertRaises(Exception):
            Task.objects.create(
                event=event, organizer=event.organizer, name="Invalida",
                due_date="2026-11-01", estimated_hours=1, type=Task.TaskType.TASK, parent=parent,
            )

    def test_db_check_constraint_blocks_bulk_create_bypass(self):
        event = make_event()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Task.objects.bulk_create([
                    Task(
                        event=event, organizer=event.organizer, name="Bulk invalida",
                        due_date="2026-11-01", estimated_hours=1,
                        type=Task.TaskType.SUBTASK, parent=None,
                    )
                ])


class AuthLoginTests(APITestCase):
    """US-11: login local y rutas protegidas."""

    def setUp(self):
        self.user, self.organizer, self.token = make_organizer_user("ana", password="secreta123")
        self.login_url = reverse("auth-login")

    def test_login_returns_token_with_valid_credentials(self):
        response = self.client.post(
            self.login_url,
            {"username": "ana", "password": "secreta123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["token"], self.token.key)

    def test_login_rejects_invalid_credentials(self):
        response = self.client.post(
            self.login_url,
            {"username": "ana", "password": "incorrecta"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_events_require_authentication(self):
        response = self.client.get(reverse("event-list-create"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.post(
            reverse("event-list-create"),
            {
                "name": "Boda",
                "event_type": "boda",
                "client_contact": "Ana",
                "event_date": "2026-12-01T18:00:00Z",
                "location": "Salón X",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_tasks_require_authentication(self):
        event = Event.objects.create(
            organizer=self.organizer,
            name="Evento",
            event_type=Event.EventType.OTRO,
            client_contact="Contacto",
            event_date="2026-12-01T18:00:00Z",
            location="Lugar",
        )
        url = reverse("task-list-create", args=[event.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.post(
            url,
            {"name": "Tarea", "due_date": "2026-11-01", "estimated_hours": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class OrganizerIsolationTests(APITestCase):
    """Un organizador no debe ver ni editar recursos de otro (404, no 403)."""

    def setUp(self):
        self.user_a, self.org_a, self.token_a = make_organizer_user("orga")
        self.user_b, self.org_b, self.token_b = make_organizer_user("orgb")
        self.event_b = Event.objects.create(
            organizer=self.org_b,
            name="Evento de B",
            event_type=Event.EventType.OTRO,
            client_contact="Cliente B",
            event_date="2026-12-01T18:00:00Z",
            location="Lugar B",
        )
        self.task_b = Task.objects.create(
            event=self.event_b,
            organizer=self.org_b,
            name="Tarea de B",
            due_date="2026-11-01",
            estimated_hours=2,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token_a.key}")

    def test_organizer_a_cannot_list_events_of_b(self):
        response = self.client.get(reverse("event-list-create"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_organizer_a_cannot_retrieve_update_or_delete_event_of_b(self):
        url = reverse("event-detail", args=[self.event_b.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], "Evento no encontrado.")

        response = self.client.patch(url, {"location": "Hack"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.event_b.refresh_from_db()
        self.assertEqual(self.event_b.location, "Lugar B")

    def test_organizer_a_cannot_access_tasks_of_b(self):
        list_url = reverse("task-list-create", args=[self.event_b.id])
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], "Evento no encontrado.")

        detail_url = reverse("task-detail", args=[self.task_b.id])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], "Tarea no encontrada.")

        response = self.client.patch(detail_url, {"name": "Hack"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Task.objects.filter(pk=self.task_b.id).exists())


class HoyViewTests(APITestCase):
    """Vista Hoy: agrupación, orden y filtros."""

    def setUp(self):
        self.user, self.organizer, self.token = make_organizer_user("hoyuser")
        self.other_user, self.other_org, _other_token = make_organizer_user("otro")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        self.today = timezone.localdate()
        self.event = Event.objects.create(
            organizer=self.organizer,
            name="Evento Hoy",
            event_type=Event.EventType.OTRO,
            client_contact="Contacto",
            event_date="2026-12-01T18:00:00Z",
            location="Lugar",
        )
        self.other_event = Event.objects.create(
            organizer=self.organizer,
            name="Otro evento",
            event_type=Event.EventType.OTRO,
            client_contact="Contacto",
            event_date="2026-12-15T18:00:00Z",
            location="Otro lugar",
        )

        self.vencida_vieja = Task.objects.create(
            event=self.event, organizer=self.organizer, name="Vencida vieja",
            due_date=self.today - timedelta(days=5), estimated_hours=4,
        )
        self.vencida_reciente = Task.objects.create(
            event=self.event, organizer=self.organizer, name="Vencida reciente",
            due_date=self.today - timedelta(days=1), estimated_hours=1,
        )
        self.hoy_pesada = Task.objects.create(
            event=self.event, organizer=self.organizer, name="Hoy pesada",
            due_date=self.today, estimated_hours=5,
        )
        self.hoy_ligera = Task.objects.create(
            event=self.event, organizer=self.organizer, name="Hoy ligera",
            due_date=self.today, estimated_hours=1,
        )
        self.proxima_cercana = Task.objects.create(
            event=self.event, organizer=self.organizer, name="Próxima cercana",
            due_date=self.today + timedelta(days=1), estimated_hours=3,
        )
        self.proxima_lejana = Task.objects.create(
            event=self.other_event, organizer=self.organizer, name="Próxima lejana",
            due_date=self.today + timedelta(days=3), estimated_hours=2,
        )
        self.hecha = Task.objects.create(
            event=self.event, organizer=self.organizer, name="Ya hecha",
            due_date=self.today, estimated_hours=1, state=Task.State.HECHA,
        )
        self.pospuesta = Task.objects.create(
            event=self.event, organizer=self.organizer, name="Pospuesta hoy",
            due_date=self.today, estimated_hours=2, state=Task.State.POSPUESTA,
        )
        Task.objects.create(
            event=Event.objects.create(
                organizer=self.other_org,
                name="Evento ajeno",
                event_type=Event.EventType.OTRO,
                client_contact="X",
                event_date="2026-12-01T18:00:00Z",
                location="Y",
            ),
            organizer=self.other_org,
            name="Tarea ajena",
            due_date=self.today,
            estimated_hours=1,
        )

    def test_hoy_requires_authentication(self):
        self.client.credentials()
        response = self.client.get(reverse("hoy"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_hoy_groups_and_orders_tasks(self):
        response = self.client.get(reverse("hoy"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["name"] for item in response.data["vencidas"]],
            ["Vencida vieja", "Vencida reciente"],
        )
        self.assertEqual(
            [item["name"] for item in response.data["para_hoy"]],
            ["Hoy ligera", "Pospuesta hoy", "Hoy pesada"],
        )
        self.assertEqual(
            [item["name"] for item in response.data["proximas"]],
            ["Próxima cercana", "Próxima lejana"],
        )
        all_names = (
            [item["name"] for item in response.data["vencidas"]]
            + [item["name"] for item in response.data["para_hoy"]]
            + [item["name"] for item in response.data["proximas"]]
        )
        self.assertNotIn("Ya hecha", all_names)
        self.assertNotIn("Tarea ajena", all_names)

    def test_hoy_filters_by_event(self):
        response = self.client.get(reverse("hoy"), {"event": self.other_event.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["vencidas"], [])
        self.assertEqual(response.data["para_hoy"], [])
        self.assertEqual(
            [item["name"] for item in response.data["proximas"]],
            ["Próxima lejana"],
        )

    def test_hoy_filters_by_state(self):
        response = self.client.get(reverse("hoy"), {"state": "pospuesta"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["vencidas"], [])
        self.assertEqual(
            [item["name"] for item in response.data["para_hoy"]],
            ["Pospuesta hoy"],
        )
        self.assertEqual(response.data["proximas"], [])

    def test_hoy_event_of_other_organizer_is_404(self):
        other_event = Event.objects.filter(organizer=self.other_org).first()
        response = self.client.get(reverse("hoy"), {"event": other_event.id})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], "Evento no encontrado.")
