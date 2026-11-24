"""Vinculación explícita y conservadora de cuentas nuevas con GLPI."""
import logging

from django.contrib.auth import get_user_model
from .glpi_client import GlpiClient, GlpiError

logger = logging.getLogger(__name__)


def vincular_cuenta_nueva(usuario):
    if usuario.glpi_user_id:
        return True
    cliente = None
    try:
        cliente = GlpiClient()
        if not cliente.available:
            return False
        cliente.init_session()
        glpi_id = cliente.find_unique_user_by_email(usuario.email)
        if glpi_id is None:
            glpi_id = cliente.create_user(usuario.nombre, usuario.email)
        if get_user_model().objects.filter(glpi_user_id=glpi_id).exclude(pk=usuario.pk).exists():
            raise GlpiError("El usuario de GLPI ya está vinculado a otra cuenta.")
        usuario.glpi_user_id = glpi_id
        usuario.save(update_fields=["glpi_user_id"])
        return True
    except Exception:
        logger.exception("No se pudo vincular a GLPI la cuenta local %s", usuario.pk)
        return False
    finally:
        if cliente is not None:
            try:
                cliente.kill_session()
            except Exception:
                logger.warning("No se pudo cerrar la sesión GLPI.")
