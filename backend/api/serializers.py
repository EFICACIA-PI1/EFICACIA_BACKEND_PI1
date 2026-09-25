from rest_framework import serializers

from .models import Event, Task


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            "id",
            "name",
            "event_type",
            "client_contact",
            "event_date",
            "location",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("El nombre del evento no puede estar vacío.")
        return value


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = [
            "id",
            "name",
            "description",
            "due_date",
            "estimated_hours",
            "state",
            "type",
            "parent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "state", "created_at", "updated_at"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("El nombre de la gestión no puede estar vacío.")
        return value

    def validate_estimated_hours(self, value):
        if value <= 0:
            raise serializers.ValidationError("Las horas estimadas deben ser mayores a 0.")
        return value

    def validate(self, attrs):
        task_type = attrs.get("type", getattr(self.instance, "type", None) or Task.TaskType.TASK)
        parent = attrs.get("parent", getattr(self.instance, "parent", None))

        if task_type == Task.TaskType.SUBTASK and parent is None:
            raise serializers.ValidationError(
                {"parent": "Una subtarea debe indicar a qué tarea pertenece."}
            )
        if task_type == Task.TaskType.TASK and parent is not None:
            raise serializers.ValidationError(
                {"parent": "Una tarea de nivel superior no puede tener una tarea padre."}
            )

        event = self.context.get("event") or getattr(self.instance, "event", None)
        if parent is not None and event is not None and parent.event_id != event.id:
            raise serializers.ValidationError(
                {"parent": "La tarea padre debe pertenecer al mismo evento."}
            )

        return attrs


class EventDetailSerializer(EventSerializer):
    tasks = TaskSerializer(many=True, read_only=True)

    class Meta(EventSerializer.Meta):
        fields = EventSerializer.Meta.fields + ["tasks"]
