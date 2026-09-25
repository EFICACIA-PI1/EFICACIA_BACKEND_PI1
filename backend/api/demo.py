from .models import Organizer

DEMO_ORGANIZER_DEFAULTS = {
    "name": "Organizador",
    "last_name": "Demo",
    "daily_hours_limit": 6,
    "user_type": "demo",
}


def get_demo_organizer():
    """Sprint 1-2: no hay login todavia, todo se asocia a un organizador fijo.

    Cuando llegue US-11 (login), esto se reemplaza por request.user sin
    tener que tocar las vistas que lo usan.
    """
    organizer, _ = Organizer.objects.get_or_create(
        user_type="demo", defaults=DEMO_ORGANIZER_DEFAULTS
    )
    return organizer
