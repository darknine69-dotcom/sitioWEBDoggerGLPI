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
    return {"DOGGER": d}