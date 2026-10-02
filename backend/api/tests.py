from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse
from django.utils import timezone
from django.test import TransactionTestCase
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import Event, Organizer, Profile, Task

User = get_user_model()

REGISTER_PAYLOAD = {
    "username": "olivia",
    "email": "olivia@example.com",
    "password": "ClaveSegura123",
    "password_confirm": "ClaveSegura123",
    "full_name": "Olivia Ruiz",
    "phone": "3001234567",
    "document_number": "1020304050",
    "address": "Cali",
}


def make_user(username, password="demo123", **extra):
    user = User.objects.create_user(username=username, password=password, **extra)
    token = Token.objects.create(user=user)
    return user, token


def make_event(user, **overrides):
    data = {
        "user": user,
        "name": "Evento de prueba",
        "event_type": Event.EventType.OTRO,
        "client_contact": "Contacto",
        "event_date": "2026-12-01T18:00:00Z",
        "location": "Lugar de prueba",
    }
    data.update(overrides)
    return Event.objects.create(**data)


class AuthenticatedAPITestCase(APITestCase):
    """Tests de eventos/tareas autenticados con token."""

    def setUp(self):
        self.user, self.token = make_user("demo")
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
        self.assertEqual(Event.objects.get().user, self.user)

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
        event = make_event(self.user)
        Task.objects.create(
            event=event, name="Reservar salón",
            due_date="2026-11-01", estimated_hours=3,
        )
        url = reverse("event-detail", args=[event.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["tasks"]), 1)

    def test_update_event(self):
        event = make_event(self.user)
        url = reverse("event-detail", args=[event.id])
        response = self.client.patch(url, {"location": "Salón nuevo"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.location, "Salón nuevo")

    def test_delete_event_then_404(self):
        event = make_event(self.user)
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
        self.event = make_event(self.user)
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
            event=self.event, name="Tarea padre",
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
            event=self.event, name="Tarea padre",
            due_date="2026-11-01", estimated_hours=2,
        )
        payload = {
            "name": "Llamar proveedor", "due_date": "2026-10-28", "estimated_hours": 1,
            "type": "subtask", "parent": parent.id,
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_subtask_parent_from_other_event_is_rejected(self):
        other_event = make_event(self.user, name="Otro evento")
        other_task = Task.objects.create(
            event=other_event, name="Tarea de otro evento",
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
            event=self.event, name="Tarea padre",
            due_date="2026-11-01", estimated_hours=2,
        )
        subtask = Task.objects.create(
            event=self.event, name="Subtarea",
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
            event=self.event, name="Reservar salón",
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
        user, _token = make_user("modelo")
        event = make_event(user)
        parent = Task.objects.create(
            event=event, name="Padre",
            due_date="2026-11-01", estimated_hours=2,
        )
        with self.assertRaises(Exception):
            Task.objects.create(
                event=event, name="Invalida",
                due_date="2026-11-01", estimated_hours=1, type=Task.TaskType.TASK, parent=parent,
            )

    def test_db_check_constraint_blocks_bulk_create_bypass(self):
        user, _token = make_user("bulk")
        event = make_event(user)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Task.objects.bulk_create([
                    Task(
                        event=event, name="Bulk invalida",
                        due_date="2026-11-01", estimated_hours=1,
                        type=Task.TaskType.SUBTASK, parent=None,
                    )
                ])


class AuthLoginTests(APITestCase):
    """Login local y rutas protegidas."""

    def setUp(self):
        self.user, self.token = make_user("ana", password="secreta123")
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
        event = make_event(self.user, name="Evento")
        url = reverse("task-list-create", args=[event.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.post(
            url,
            {"name": "Tarea", "due_date": "2026-11-01", "estimated_hours": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserIsolationTests(APITestCase):
    """Un usuario no debe ver ni editar recursos de otro (404, no 403)."""

    def setUp(self):
        self.user_a, self.token_a = make_user("usera")
        self.user_b, self.token_b = make_user("userb")
        self.event_b = make_event(self.user_b, name="Evento de B", location="Lugar B")
        self.task_b = Task.objects.create(
            event=self.event_b,
            name="Tarea de B",
            due_date="2026-11-01",
            estimated_hours=2,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token_a.key}")

    def test_user_a_cannot_list_events_of_b(self):
        response = self.client.get(reverse("event-list-create"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_user_a_cannot_retrieve_update_or_delete_event_of_b(self):
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

    def test_user_a_cannot_access_tasks_of_b(self):
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
        self.user, self.token = make_user("hoyuser")
        self.other_user, _other_token = make_user("otro")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        self.today = timezone.localdate()
        self.event = make_event(self.user, name="Evento Hoy")
        self.other_event = make_event(
            self.user, name="Otro evento", event_date="2026-12-15T18:00:00Z", location="Otro lugar"
        )

        self.vencida_vieja = Task.objects.create(
            event=self.event, name="Vencida vieja",
            due_date=self.today - timedelta(days=5), estimated_hours=4,
        )
        self.vencida_reciente = Task.objects.create(
            event=self.event, name="Vencida reciente",
            due_date=self.today - timedelta(days=1), estimated_hours=1,
        )
        self.hoy_pesada = Task.objects.create(
            event=self.event, name="Hoy pesada",
            due_date=self.today, estimated_hours=5,
        )
        self.hoy_ligera = Task.objects.create(
            event=self.event, name="Hoy ligera",
            due_date=self.today, estimated_hours=1,
        )
        self.proxima_cercana = Task.objects.create(
            event=self.event, name="Próxima cercana",
            due_date=self.today + timedelta(days=1), estimated_hours=3,
        )
        self.proxima_lejana = Task.objects.create(
            event=self.other_event, name="Próxima lejana",
            due_date=self.today + timedelta(days=3), estimated_hours=2,
        )
        self.hecha = Task.objects.create(
            event=self.event, name="Ya hecha",
            due_date=self.today, estimated_hours=1, state=Task.State.HECHA,
        )
        self.pospuesta = Task.objects.create(
            event=self.event, name="Pospuesta hoy",
            due_date=self.today, estimated_hours=2, state=Task.State.POSPUESTA,
        )
        Task.objects.create(
            event=make_event(self.other_user, name="Evento ajeno", location="Y"),
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

    def test_hoy_event_of_other_user_is_404(self):
        other_event = Event.objects.filter(user=self.other_user).first()
        response = self.client.get(reverse("hoy"), {"event": other_event.id})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], "Evento no encontrado.")


class SignalAndOwnershipTests(APITestCase):
    def test_create_user_gets_profile_and_can_list_events(self):
        user = User.objects.create_user(username="shelluser", password="demo123")
        self.assertTrue(Profile.objects.filter(user=user).exists())
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.get(reverse("event-list-create"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_legacy_event_keeps_owner_from_organizer_user(self):
        user, _token = make_user("legacy")
        organizer = Organizer.objects.create(
            user=user, name="Organizador", last_name="Legacy", user_type="organizador"
        )
        event = make_event(user, organizer=organizer, name="Evento legado")
        self.assertEqual(event.user_id, organizer.user_id)
        self.assertEqual(event.user_id, user.id)


class RegisterTests(APITestCase):
    def setUp(self):
        self.url = reverse("auth-register")

    def test_register_creates_user_profile_and_token(self):
        response = self.client.post(self.url, REGISTER_PAYLOAD, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("token", response.data)
        self.assertEqual(response.data["user"]["username"], "olivia")
        self.assertEqual(response.data["user"]["email"], "olivia@example.com")
        self.assertEqual(response.data["user"]["document_number"], "1020304050")
        user = User.objects.get(username="olivia")
        self.assertEqual(user.profile.full_name, "Olivia Ruiz")
        self.assertEqual(user.profile.phone, "3001234567")

    def test_register_ignores_invalid_authorization_header(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token inválido")
        response = self.client.post(self.url, REGISTER_PAYLOAD, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_register_duplicate_username_email_document(self):
        self.client.post(self.url, REGISTER_PAYLOAD, format="json")
        dup_username = {**REGISTER_PAYLOAD, "email": "otra@example.com", "document_number": "1099887766"}
        response = self.client.post(self.url, dup_username, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)

        dup_email = {
            **REGISTER_PAYLOAD,
            "username": "otra",
            "email": "OLIVIA@example.com",
            "document_number": "1099887766",
        }
        response = self.client.post(self.url, dup_email, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

        dup_doc = {
            **REGISTER_PAYLOAD,
            "username": "otra",
            "email": "otra@example.com",
        }
        response = self.client.post(self.url, dup_doc, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("document_number", response.data)

    def test_register_password_mismatch_and_weak(self):
        payload = {**REGISTER_PAYLOAD, "password_confirm": "OtraClave123"}
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)

        payload = {**REGISTER_PAYLOAD, "username": "debil", "email": "debil@example.com",
                   "document_number": "1122334455", "password": "123", "password_confirm": "123"}
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_register_rejects_letters_in_phone_and_document(self):
        payload = {**REGISTER_PAYLOAD, "phone": "300ABC4567"}
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)

        payload = {**REGISTER_PAYLOAD, "phone": "3001234567", "document_number": "12AB34"}
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("document_number", response.data)


class ProfileMeTests(APITestCase):
    def setUp(self):
        self.user, self.token = make_user("perfil", email="perfil@example.com")
        self.user.profile.full_name = "Perfil Uno"
        self.user.profile.phone = "3001112233"
        self.user.profile.document_number = "12345678"
        self.user.profile.address = "Bogotá"
        self.user.profile.save()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        self.url = reverse("auth-me")

    def test_get_me(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "perfil")
        self.assertEqual(response.data["full_name"], "Perfil Uno")
        self.assertEqual(response.data["document_number"], "12345678")

    def test_patch_me(self):
        response = self.client.patch(
            self.url,
            {"full_name": "Nombre Nuevo", "phone": "3119998877", "address": "Medellín", "email": "nuevo@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["full_name"], "Nombre Nuevo")
        self.assertEqual(response.data["email"], "nuevo@example.com")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "nuevo@example.com")

    def test_cannot_change_document_or_username(self):
        response = self.client.patch(self.url, {"document_number": "99999999"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("document_number", response.data)

        response = self.client.patch(self.url, {"username": "hacker"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)

    def test_same_document_and_username_are_ignored(self):
        response = self.client.patch(
            self.url,
            {"document_number": "12345678", "username": "perfil", "full_name": "Sigue igual"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["full_name"], "Sigue igual")
        self.assertEqual(response.data["username"], "perfil")

    def test_email_taken_by_other_user(self):
        make_user("otro", email="ocupado@example.com")
        response = self.client.patch(self.url, {"email": "ocupado@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_me_requires_authentication(self):
        self.client.credentials()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordAndLogoutTests(APITestCase):
    def setUp(self):
        self.user, self.token = make_user("claveuser", password="ClaveAntigua123", email="clave@example.com")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_change_password_rotates_token(self):
        response = self.client.post(
            reverse("auth-change-password"),
            {
                "old_password": "ClaveAntigua123",
                "new_password": "ClaveNueva456",
                "new_password_confirm": "ClaveNueva456",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        new_token = response.data["token"]
        self.assertNotEqual(new_token, self.token.key)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        blocked = self.client.get(reverse("auth-me"))
        self.assertEqual(blocked.status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {new_token}")
        ok = self.client.get(reverse("auth-me"))
        self.assertEqual(ok.status_code, status.HTTP_200_OK)

    def test_change_password_rejects_wrong_old(self):
        response = self.client.post(
            reverse("auth-change-password"),
            {
                "old_password": "incorrecta",
                "new_password": "ClaveNueva456",
                "new_password_confirm": "ClaveNueva456",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("old_password", response.data)

    def test_password_reset_same_response_and_sends_mail(self):
        self.client.credentials()
        url = reverse("auth-password-reset")
        existing_response = self.client.post(
            url, {"email": "clave@example.com"}, format="json"
        )
        response = existing_response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("registrado", response.data["detail"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Recuperación de contraseña - EFICACIA")

        response = self.client.post(url, {"email": "noexiste@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, existing_response.data)
        self.assertEqual(len(mail.outbox), 1)

    def test_password_reset_confirm_then_login(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        self.client.credentials()
        response = self.client.post(
            reverse("auth-password-reset-confirm"),
            {
                "uid": uid,
                "token": token,
                "new_password": "ClaveReset789",
                "new_password_confirm": "ClaveReset789",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        login = self.client.post(
            reverse("auth-login"),
            {"username": "claveuser", "password": "ClaveReset789"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

        reused = self.client.post(
            reverse("auth-password-reset-confirm"),
            {
                "uid": uid,
                "token": token,
                "new_password": "OtraClave789",
                "new_password_confirm": "OtraClave789",
            },
            format="json",
        )
        self.assertEqual(reused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("enlace", reused.data["detail"])

    def test_password_reset_confirm_invalid_token(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        self.client.credentials()
        response = self.client.post(
            reverse("auth-password-reset-confirm"),
            {
                "uid": uid,
                "token": "token-invalido",
                "new_password": "ClaveReset789",
                "new_password_confirm": "ClaveReset789",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_invalidates_token(self):
        response = self.client.post(reverse("auth-logout"))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        response = self.client.get(reverse("auth-me"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class OwnershipDataMigrationTests(TransactionTestCase):
    migrate_from = [("api", "0005_organizer_user")]
    migrate_to = [("api", "0006_event_user_profile_and_ownership")]

    def setUp(self):
        MigrationExecutor(connection).migrate(self.migrate_from)
        old_apps = MigrationExecutor(connection).loader.project_state(self.migrate_from).apps
        UserModel = old_apps.get_model("auth", "User")
        OrganizerModel = old_apps.get_model("api", "Organizer")
        EventModel = old_apps.get_model("api", "Event")

        legacy_user = UserModel.objects.create(username="legacy", password="!")
        linked_organizer = OrganizerModel.objects.create(
            user_id=legacy_user.pk,
            name="Ana",
            last_name="Ruiz",
            daily_hours_limit=6,
            user_type="organizador",
        )
        unlinked_organizer = OrganizerModel.objects.create(
            name="Demo",
            last_name="Antiguo",
            daily_hours_limit=6,
            user_type="demo",
        )
        self.linked_event_id = EventModel.objects.create(
            organizer_id=linked_organizer.pk,
            name="Evento de Ana",
            event_type="boda",
            client_contact="Ana",
            event_date="2026-12-01T18:00:00Z",
            location="Cali",
        ).pk
        self.unlinked_event_id = EventModel.objects.create(
            organizer_id=unlinked_organizer.pk,
            name="Evento demo",
            event_type="otro",
            client_contact="Contacto",
            event_date="2026-12-02T18:00:00Z",
            location="Bogotá",
        ).pk
        self.legacy_user_id = legacy_user.pk
        self.unlinked_organizer_id = unlinked_organizer.pk

        OrganizerModel.objects.create(
            name="Sin",
            last_name="Eventos",
            daily_hours_limit=6,
            user_type="sin_eventos",
        )

    def tearDown(self):
        MigrationExecutor(connection).migrate(self.migrate_to)
        super().tearDown()

    def test_backfill_preserves_event_owners_and_creates_only_needed_users(self):
        MigrationExecutor(connection).migrate(self.migrate_to)
        new_apps = MigrationExecutor(connection).loader.project_state(self.migrate_to).apps
        UserModel = new_apps.get_model("auth", "User")
        OrganizerModel = new_apps.get_model("api", "Organizer")
        EventModel = new_apps.get_model("api", "Event")
        ProfileModel = new_apps.get_model("api", "Profile")

        linked_event = EventModel.objects.get(pk=self.linked_event_id)
        self.assertEqual(linked_event.user_id, self.legacy_user_id)
        self.assertEqual(
            ProfileModel.objects.get(user_id=self.legacy_user_id).full_name,
            "Ana Ruiz",
        )

        unlinked_event = EventModel.objects.get(pk=self.unlinked_event_id)
        fallback_user = UserModel.objects.get(pk=unlinked_event.user_id)
        self.assertEqual(
            fallback_user.username,
            f"organizador_{self.unlinked_organizer_id}",
        )
        self.assertFalse(fallback_user.is_active)
        self.assertEqual(fallback_user.password, "!")
        self.assertIsNone(
            OrganizerModel.objects.get(user_type="sin_eventos").user_id
        )
