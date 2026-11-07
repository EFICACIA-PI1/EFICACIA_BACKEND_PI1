from datetime import date, timedelta
from decimal import Decimal

from api.models import Task
from api.views import (
    _format_hours,
    daily_limit_reduction_payload,
    events_with_progress,
    planned_hours_by_date,
    planned_hours_for_date,
)


def test_hour_helpers_exclude_completed_tasks(user, event, task):
    completed = Task.objects.create(
        event=event,
        name="Completada",
        due_date=task.due_date,
        estimated_hours=Decimal("5.00"),
        state=Task.State.HECHA,
    )

    assert planned_hours_for_date(user, task.due_date) == Decimal("2")
    assert planned_hours_for_date(user, task.due_date, exclude_task=task) == Decimal("0")
    assert planned_hours_by_date(
        user, task.due_date, task.due_date
    ) == {task.due_date: Decimal("2")}
    assert completed.pk
    assert _format_hours(Decimal("2.00")) == "2"


def test_events_with_progress_counts_tasks(event, task):
    Task.objects.create(
        event=event,
        name="Terminada",
        due_date=task.due_date,
        estimated_hours=Decimal("1.00"),
        state=Task.State.HECHA,
    )

    annotated = events_with_progress(event.user).get(pk=event.pk)

    assert annotated.task_total == 2
    assert annotated.task_done == 1


def test_daily_limit_reduction_reports_future_overload(user, event):
    due_date = date.today() + timedelta(days=1)
    Task.objects.create(
        event=event,
        name="Carga",
        due_date=due_date,
        estimated_hours=Decimal("7.00"),
    )

    message = daily_limit_reduction_payload(user, 6)

    assert message is not None
    assert str(due_date) in message
    assert daily_limit_reduction_payload(user, 8) is None
