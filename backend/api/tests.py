from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .demo import get_demo_organizer
from .models import Event, Task


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


class EventAPITests(APITestCase):
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


class TaskAPITests(APITestCase):
    """US-02: crear plan inicial de subtareas. US-03: editar/eliminar subtarea."""

    def setUp(self):
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
