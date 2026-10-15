"""Cifrado transparente para secretos guardados en BD (tokens de GLPI).

`CampoCifrado` se comporta como un TextField normal: al guardar cifra con
Fernet y al leer descifra. Los valores viejos en texto plano se siguen
leyendo igual y se re-cifran solos al próximo guardado (migración
transparente, sin script de datos).

Clave: `DOGGER_FERNET_KEY` del entorno (Fernet urlsafe-base64 de 32
bytes; se genera con `python -c "from cryptography.fernet import
Fernet; print(Fernet.generate_key().decode())"`). Sin ella se deriva
una estable del SECRET_KEY: mejor que texto plano, pero en producción
fija la variable para no atar el cifrado al secret de Django.
"""

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)

PREFIJO = "dgr1:"


def _llave():
    cruda = (os.getenv("DOGGER_FERNET_KEY") or "").strip()
    if cruda:
        try:
            key = cruda.encode()
            Fernet(key)  # valida formato
            return key
        except Exception:
            logger.error("DOGGER_FERNET_KEY inválida: se deriva del SECRET_KEY")
    digest = hashlib.sha256(f"dogger-fernet:{settings.SECRET_KEY}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet():
    return Fernet(_llave())


def cifrar(valor):
    if not valor:
        return valor
    texto = str(valor)
    if texto.startswith(PREFIJO):
        return texto
    return PREFIJO + _fernet().encrypt(texto.encode()).decode()


def descifrar(valor):
    if not valor or not str(valor).startswith(PREFIJO):
        return valor  # vacío o legado en texto plano
    try:
        return _fernet().decrypt(str(valor)[len(PREFIJO):].encode()).decode()
    except InvalidToken:
        logger.error("Token cifrado ilegible (¿cambió la llave?). Se ignora.")
        return ""


class CampoCifrado(models.TextField):
    """TextField que cifra al guardar y descifra al leer."""

    description = "Texto cifrado con Fernet"

    def from_db_value(self, value, expression, connection):
        return descifrar(value)

    def to_python(self, value):
        value = super().to_python(value)
        return descifrar(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return cifrar(value)
