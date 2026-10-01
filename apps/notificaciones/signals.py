"""Primera vez que entra una persona: mensaje de bienvenida en la campana
y correo personalizado de bienvenida."""

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone


@receiver(user_logged_in)
def bienvenida_primer_ingreso(sender, request, user, **kwargs):
    if not getattr(user, "is_authenticated", False):
        return
    marca = getattr(user, "bienvenida_vista", None)
    if marca:
        return
    try:
        from . import emails, services

        # 1) aviso con icono en la campana (sale como ventana emergente)
        services.bienvenida(user)
        # 2) correo de bienvenida con diseño
        emails.correo_bienvenida(user)
    except Exception:
        # Un aviso fallido nunca debe impedir el ingreso.
        pass
    try:
        user.bienvenida_vista = timezone.now()
        user.save(update_fields=["bienvenida_vista"])
    except Exception:
        pass
