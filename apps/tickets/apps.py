from django.apps import AppConfig


class TicketsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tickets"
    label = "tickets"
    verbose_name = "Tickets"

    def ready(self):
        # Conecta la invalidación del caché (puntos del observador, etc.).
        import apps.tickets.signals  # noqa: F401
