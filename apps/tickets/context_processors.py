from django.conf import settings


def dogger_config(request):
    """Expone settings.DOGGER combinado con la configuración de la página
    editable desde el panel (apps.tickets.models.ConfigSitio).

    Los valores gestionados en la pestaña "Página" de Ajustes tienen
    prioridad sobre los valores por defecto de settings.py / variables de
    entorno.
    """
    d = dict(settings.DOGGER)
    try:
        from apps.tickets.models import ConfigSitio

        cfg = ConfigSitio.cargar()
        d.update({
            "pagina_mostrar_redes": cfg.pagina_mostrar_redes,
            "correo_activo": cfg.correo_activo,
            "correo_soporte": cfg.correo_soporte,
            "whatsapp_activo": cfg.whatsapp_activo,
            "whatsapp_soporte": cfg.whatsapp_numero,
            "tiktok_activo": cfg.tiktok_activo,
            "tiktok": cfg.tiktok_url,
            "instagram_activo": cfg.instagram_activo,
            "instagram": cfg.instagram_url,
            "facebook_activo": cfg.facebook_activo,
            "facebook": cfg.facebook_url,
        })
    except Exception:
        # Si la tabla aún no existe (antes de migrar), se mantiene lo de settings.
        pass
    return {"DOGGER": d, **_contador_papelera(request)}


def _contador_papelera(request):
    """Tickets en la papelera, para el contador de la navbar (solo admins).

    Va en un context processor, pero se omite en la propia página de la
    papelera, que ya trae el total en su contexto (ahí se cuenta aparte).
    """
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {"papelera_total": 0}
    if getattr(usuario, "rol", None) != "admin" or not getattr(usuario, "activo", False):
        return {"papelera_total": 0}
    match = getattr(request, "resolver_match", None)
    if match is not None and match.url_name == "papelera":
        return {}
    try:
        from apps.tickets.models import Ticket

        total = Ticket.en_papelera().count()
    except Exception:
        # Antes de aplicar la migración la columna no existe.
        return {"papelera_total": 0}
    return {"papelera_total": total}