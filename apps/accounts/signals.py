"""Información del inicio de cada sesión autenticada."""
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone


@receiver(user_logged_in, dispatch_uid="accounts.session_login_time")
def guardar_inicio_sesion(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session"):
        request.session["inicio_sesion"] = timezone.now().isoformat()
