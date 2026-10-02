import re

from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()

PHONE_RE = re.compile(r"^\+?\d{7,15}$")
DOCUMENT_RE = re.compile(r"^\d{6,12}$")


def validate_full_name(value):
    name = (value or "").strip()
    if len(name) < 3 or len(name) > 150:
        raise serializers.ValidationError(
            "El nombre completo debe tener entre 3 y 150 caracteres."
        )
    return name


def validate_phone(value):
    if not PHONE_RE.fullmatch(value or ""):
        raise serializers.ValidationError(
            "El teléfono debe tener entre 7 y 15 dígitos, con un '+' opcional al inicio."
        )
    return value


def validate_document_number(value):
    if not DOCUMENT_RE.fullmatch(value or ""):
        raise serializers.ValidationError(
            "El número de documento debe tener entre 6 y 12 dígitos."
        )
    return value


def normalize_email(value):
    email = (value or "").strip().lower()
    if not email:
        raise serializers.ValidationError("El correo es obligatorio.")
    return email


def validate_email_unique(email, exclude_user=None):
    qs = User.objects.filter(email__iexact=email)
    if exclude_user is not None:
        qs = qs.exclude(pk=exclude_user.pk)
    if qs.exists():
        raise serializers.ValidationError("Ya existe una cuenta con ese correo.")
    return email
