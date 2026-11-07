"""Pruebas unitarias de api/validators.py — Martín Álvarez (FCCPRCT2-17)."""

import pytest
from rest_framework import serializers

from api.validators import (
    normalize_email,
    validate_email_unique,
    validate_full_name,
    validate_phone,
)


# ---------- validate_full_name ----------

def test_full_name_valido_se_devuelve_sin_espacios():
    assert validate_full_name("  Martín Álvarez  ") == "Martín Álvarez"


@pytest.mark.parametrize("valor", ["", None, "Al", "   ab   ", "x" * 151])
def test_full_name_invalido_lanza_error(valor):
    with pytest.raises(serializers.ValidationError):
        validate_full_name(valor)


def test_full_name_en_los_limites_es_valido():
    assert validate_full_name("Ana") == "Ana"
    assert validate_full_name("x" * 150) == "x" * 150


# ---------- validate_phone ----------

@pytest.mark.parametrize("valor", ["3154000000", "+573154000000", "1234567"])
def test_phone_valido_se_devuelve_igual(valor):
    assert validate_phone(valor) == valor


@pytest.mark.parametrize(
    "valor", ["", None, "123456", "1" * 16, "315-400-0000", "telefono", "++5731540000"]
)
def test_phone_invalido_lanza_error(valor):
    with pytest.raises(serializers.ValidationError):
        validate_phone(valor)


# ---------- normalize_email ----------

def test_normalize_email_quita_espacios_y_pasa_a_minusculas():
    assert normalize_email("  Martin.Alvarez@CorreoUnivalle.EDU.co ") == (
        "martin.alvarez@correounivalle.edu.co"
    )


@pytest.mark.parametrize("valor", ["", "   ", None])
def test_normalize_email_vacio_lanza_error(valor):
    with pytest.raises(serializers.ValidationError):
        normalize_email(valor)


# ---------- validate_email_unique (usa base de datos) ----------

def test_email_libre_es_valido(db):
    assert validate_email_unique("nuevo@example.com") == "nuevo@example.com"


def test_email_repetido_lanza_error_sin_importar_mayusculas(user):
    # el fixture `user` tiene el correo olivia@example.com
    with pytest.raises(serializers.ValidationError):
        validate_email_unique("OLIVIA@example.com")


def test_email_del_mismo_usuario_es_valido_al_editar(user):
    assert validate_email_unique("olivia@example.com", exclude_user=user) == (
        "olivia@example.com"
    )


def test_email_de_otro_usuario_sigue_siendo_invalido_al_editar(user, second_user):
    with pytest.raises(serializers.ValidationError):
        validate_email_unique(user.email, exclude_user=second_user)
