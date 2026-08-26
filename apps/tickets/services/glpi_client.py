"""
Cliente REST para GLPI (API clásica apirest.php).

Uso opcional: si GLPI_ENABLED=True en settings/.env, al crear o actualizar
tickets en Dogger se puede sincronizar hacia GLPI.

Documentación GLPI: /apirest.php/ y help.glpi-project.org
"""
from __future__ import annotations

import logging
import posixpath
import re
from typing import Any

import requests
from django.conf import settings

try:
    from requests.exceptions import RequestException
except ImportError:
    RequestException = Exception

logger = logging.getLogger(__name__)


class GlpiError(Exception):
    pass


def normalizar_base_url(url: str) -> str:
    """
    Convierte URLs de la nueva API de GLPI 11 (/api.php/v1) a la API
    clásica REST (/apirest.php), que es la que usa este cliente.
    Ej: http://host/api.php/v1 → http://host/apirest.php
    """
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    corregida = re.sub(r"/api\.php/v\d+$", "/apirest.php", url)
    if corregida != url:
        logger.warning(
            "GLPI_BASE_URL '%s' usa el formato nuevo (api.php); se usará '%s' "
            "(API clásica apirest.php, compatible con este cliente).",
            url, corregida,
        )
    return corregida


class GlpiClient:
    """Sesión mínima: initSession → operaciones → killSession."""

    def __init__(self):
        cfg = getattr(settings, "GLPI", {}) or {}
        self.enabled = bool(cfg.get("enabled"))
        self.base_url = normalizar_base_url(cfg.get("base_url") or "")
        self.app_token = cfg.get("app_token") or ""
        self.user_token = cfg.get("user_token") or ""
        self.timeout = int(cfg.get("timeout", 30))
        self._session_token: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.enabled and self.base_url and self.app_token and self.user_token)

    def _headers(self, with_session: bool = True) -> dict:
        h = {
            "Content-Type": "application/json",
            "App-Token": self.app_token,
        }
        if with_session and self._session_token:
            h["Session-Token"] = self._session_token
        return h

    def init_session(self) -> str:
        if not self.available:
            raise GlpiError("GLPI no está configurado o está deshabilitado")
        url = f"{self.base_url}/initSession"
        # Auth por user_token
        headers = {
            "Content-Type": "application/json",
            "App-Token": self.app_token,
            "Authorization": f"user_token {self.user_token}",
        }
        r = requests.get(url, headers=headers, timeout=self.timeout)
        if r.status_code != 200:
            raise GlpiError(f"initSession falló ({r.status_code}): {r.text[:300]}")
        data = r.json()
        token = data.get("session_token")
        if not token:
            raise GlpiError("initSession no devolvió session_token")
        self._session_token = token
        return token

    def kill_session(self) -> None:
        if not self._session_token:
            return
        try:
            requests.get(
                f"{self.base_url}/killSession",
                headers=self._headers(),
                timeout=self.timeout,
            )
        except Exception as exc:
            logger.warning("killSession: %s", exc)
        finally:
            self._session_token = None

    def find_user_by_email(self, email: str) -> int | None:
        """Busca un usuario GLPI por correo y retorna su id (o None)."""
        if not email:
            return None
        url = f"{self.base_url}/search/User"
        params = {
            "criteria[0][link]": "AND",
            "criteria[0][field]": "5",
            "criteria[0][searchtype]": "contains",
            "criteria[0][value]": email.strip(),
            "forcedisplay[0]": "1",
        }
        r = requests.get(
            url, headers=self._headers(), params=params, timeout=self.timeout
        )
        if r.status_code != 200:
            logger.warning("search/User GLPI falló (%s): %s", r.status_code, r.text[:200])
            return None
        data = r.json().get("data") or {}
        rows = data.values() if isinstance(data, dict) else data
        for row in rows:
            try:
                return int(row.get("id"))
            except (TypeError, ValueError, AttributeError):
                continue
        return None

    def create_user(self, nombre: str, email: str) -> int:
        """
        Crea un usuario en GLPI a partir de una cuenta local del panel.
        Login derivado del correo. Retorna el glpi_user_id creado.
        Lanza GlpiError si falla.
        """
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            raise GlpiError("Correo inválido para crear usuario en GLPI.")
        login = email.split("@")[0]
        partes = (nombre or login).split()
        base_input = {
            "name": login,
            "realname": partes[-1],
            "firstname": " ".join(partes[:-1]),
            "_useremails": [email],
        }
        url = f"{self.base_url}/User"
        r = requests.post(url, headers=self._headers(), json={"input": [base_input]}, timeout=self.timeout)
        if r.status_code not in (200, 201):
            # Reintento sin correo (GLPI antiguo no soporta _useremails)
            fallback = {k: v for k, v in base_input.items() if k != "_useremails"}
            r2 = requests.post(url, headers=self._headers(), json={"input": [fallback]}, timeout=self.timeout)
            if r2.status_code not in (200, 201):
                raise GlpiError(f"GLPI rechazó la creación de usuario ({r.status_code}): {r.text[:200]}")
            data = r2.json()
        else:
            data = r.json()

        glpi_id = None
        if isinstance(data, dict):
            glpi_id = data.get("id")
        elif isinstance(data, list) and data:
            glpi_id = data[0].get("id")
        try:
            glpi_id = int(glpi_id)
        except (TypeError, ValueError):
            raise GlpiError("GLPI no devolvió un id de usuario válido.")

        # Correo por si el _useremails no aplicó
        if "_useremails" not in base_input or r.status_code >= 400:
            try:
                requests.post(
                    f"{self.base_url}/UserEmail",
                    headers=self._headers(),
                    json={"input": [{"users_id": glpi_id, "email": email, "is_default": 1}]},
                    timeout=self.timeout,
                )
            except RequestException:
                logger.warning("No se pudo asignar el correo al usuario GLPI #%s", glpi_id)
        return glpi_id

    def list_users(self) -> list[dict[str, Any]]:
        """
        Lista usuarios de GLPI para importarlos como cuentas técnicas.
        Prueba /search/User con varias combinaciones y como último recurso
        el endpoint directo /User/. Lanza GlpiError si todo falla.
        Retorna [{glpi_id, login, email, nombre_real}, ...]
        """
        url = f"{self.base_url}/search/User"
        intentos = [
            # 1: búsqueda completa (login 1, email 5, nombre real 34, activo 8)
            {
                "list_size": "500",
                "forcedisplay[0]": "1",
                "forcedisplay[1]": "5",
                "forcedisplay[2]": "34",
                "forcedisplay[3]": "8",
            },
            # 2: solo activos
            {
                "list_size": "500",
                "forcedisplay[0]": "1",
                "forcedisplay[1]": "5",
                "forcedisplay[2]": "8",
                "criteria[0][field]": "8",
                "criteria[0][searchtype]": "equals",
                "criteria[0][value]": "1",
            },
            # 3: mínima (algunas versiones rechazan campos extra)
            {"list_size": "500", "forcedisplay[0]": "1"},
        ]
        ultimo_error = ""
        data: Any = {}
        for params in intentos:
            try:
                r = requests.get(url, headers=self._headers(), params=params, timeout=self.timeout)
            except RequestException as exc:
                ultimo_error = f"sin conexión: {exc}"
                continue
            if r.status_code == 200:
                try:
                    crudo = r.json()
                except ValueError:
                    ultimo_error = "respuesta no-JSON de /search/User"
                    logger.warning("search/User GLPI devolvió contenido no-JSON")
                    continue
                data = crudo.get("data") if isinstance(crudo, dict) else crudo
                data = data or {}
                if data:
                    break
                continue
            ultimo_error = f"{r.status_code}: {r.text[:200]}"
            logger.warning("search/User GLPI (%s): %s", r.status_code, r.text[:200])

        if not data:
            # Último recurso: endpoint directo /User/
            try:
                r = requests.get(
                    f"{self.base_url}/User/",
                    headers={**self._headers(), "Accept": "application/json"},
                    params={"range": "0-499", "is_deleted": "0"},
                    timeout=self.timeout,
                )
                if r.status_code == 200:
                    try:
                        items = r.json()
                    except ValueError:
                        ultimo_error = "respuesta no-JSON de /User/"
                        items = []
                    filas = [
                        {
                            "id": u.get("id"),
                            "1": u.get("name") or "",
                            "5": "",
                            "34": " ".join(
                                p for p in [u.get("firstname") or "", u.get("realname") or ""] if p
                            ),
                            "8": u.get("is_active"),
                        }
                        for u in (items if isinstance(items, list) else [])
                    ]
                    data = filas
                else:
                    ultimo_error = f"/User/: {r.status_code}: {r.text[:200]}"
            except RequestException as exc:
                ultimo_error = f"/User/: sin conexión: {exc}"

        if not data:
            raise GlpiError(f"No se pudo listar usuarios de GLPI ({ultimo_error})")

        rows = (
            [dict(row, id=int(k)) for k, row in data.items()]
            if isinstance(data, dict)
            else list(data)
        )
        resultado = []
        filas_malas = 0
        for row in rows:
            glpi_id = None
            for clave in ("id", "users_id"):
                try:
                    glpi_id = int(row.get(clave))
                    break
                except (TypeError, ValueError, KeyError):
                    continue
            if glpi_id is None:
                filas_malas += 1
                continue
            # Estado activo en GLPI (campo 8): "1"/"0"; None si no vino el campo
            raw_activo = str(row.get("8") or "").strip()
            resultado.append(
                {
                    "glpi_id": glpi_id,
                    "login": str(row.get("1") or "").strip(),
                    "email": str(row.get("5") or "").strip(),
                    "nombre_real": str(row.get("34") or "").strip(),
                    "activo_glpi": (raw_activo == "1") if raw_activo else None,
                }
            )
        if rows and not resultado:
            # Tu GLPI omite el campo "id" en /search/User:
            # resolver los IDs con el endpoint directo /User/ cruzando por login.
            resultado = self._resolver_ids_via_user(rows)
        # Roster completo: añadir usuarios que solo existen en /User/
        # (la búsqueda de GLPI a veces omite perfiles recientes o sin campos).
        vistos = {u["glpi_id"] for u in resultado}
        for directo in self._usuarios_directos():
            if directo["glpi_id"] not in vistos:
                resultado.append(directo)
        if not resultado and rows:
            raise GlpiError(
                "GLPI devolvió filas con formato inesperado. "
                f"Primera fila: {str(rows[0])[:200]}"
            )
        return resultado

    def _usuarios_directos(self) -> list[dict[str, Any]]:
        """GET /User/: roster con id, login, nombre real y estado activo (sin correos)."""
        try:
            r = requests.get(
                f"{self.base_url}/User/",
                headers={**self._headers(), "Accept": "application/json"},
                params={"range": "0-499", "is_deleted": "0"},
                timeout=self.timeout,
            )
            if r.status_code != 200:
                logger.warning("/User/ GLPI: %s: %s", r.status_code, r.text[:200])
                return []
            items = r.json()
        except (RequestException, ValueError) as exc:
            logger.warning("/User/ GLPI sin conexión: %s", exc)
            return []
        if not isinstance(items, list):
            return []
        salida = []
        for u in items:
            try:
                uid = int(u.get("id"))
            except (TypeError, ValueError):
                continue
            try:
                activo = bool(int(u.get("is_active", 1) or 0))
            except (TypeError, ValueError):
                activo = True
            nombre_real = str(
                " ".join(
                    p
                    for p in [str(u.get("firstname") or "").strip(), str(u.get("realname") or "").strip()]
                    if p
                )
            ).strip()
            salida.append(
                {
                    "glpi_id": uid,
                    "login": str(u.get("name") or "").strip(),
                    "email": "",
                    "nombre_real": nombre_real,
                    "activo_glpi": activo,
                }
            )
        return salida

    def _resolver_ids_via_user(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Cuando /search/User no incluye la columna id, se consulta GET /User/
        (que sí trae id, name, is_active, realname y firstname) y se cruzan
        ambas respuestas por login.
        """
        try:
            r = requests.get(
                f"{self.base_url}/User/",
                headers={**self._headers(), "Accept": "application/json"},
                params={"range": "0-499", "is_deleted": "0"},
                timeout=self.timeout,
            )
            if r.status_code != 200:
                logger.warning("/User/ GLPI para resolver ids: %s: %s", r.status_code, r.text[:200])
                return []
            items = r.json()
        except (RequestException, ValueError) as exc:
            logger.warning("/User/ GLPI sin conexión: %s", exc)
            return []

        if not isinstance(items, list):
            return []
        por_login = {}
        for u in items:
            try:
                uid = int(u.get("id"))
            except (TypeError, ValueError):
                continue
            login = str(u.get("name") or "").strip().lower()
            if not login:
                continue
            try:
                activo_directo = bool(int(u.get("is_active", 1) or 0))
            except (TypeError, ValueError):
                activo_directo = True
            nombre_real = " ".join(
                p for p in [str(u.get("firstname") or "").strip(), str(u.get("realname") or "").strip()] if p
            )
            por_login[login] = {"id": uid, "activo": activo_directo, "nombre_real": nombre_real}

        resultado = []
        for row in rows:
            login = str(row.get("1") or "").strip()
            info = por_login.get(login.lower())
            if not info:
                continue
            raw_activo = str(row.get("8") or "").strip() if row.get("8") is not None else ""
            resultado.append(
                {
                    "glpi_id": info["id"],
                    "login": login,
                    "email": str(row.get("5") or "").strip(),
                    "nombre_real": str(row.get("34") or "").strip() or info["nombre_real"],
                    "activo_glpi": (raw_activo == "1") if raw_activo else info["activo"],
                }
            )
        return resultado

    def create_ticket(
        self,
        name: str,
        content: str,
        urgency: int = 3,
        itilcategories_id: int | None = None,
        entities_id: int = 0,
        type_: int = 1,
        requesters_id: int | None = None,
        assignees_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """
        Crea un Ticket en GLPI.
        urgency: 1=muy baja … 5=muy alta
        type: 1=incidente, 2=solicitud
        """
        payload: dict[str, Any] = {
            "input": {
                "name": name[:255],
                "content": content,
                "urgency": urgency,
                "type": type_,
                "entities_id": entities_id,
            }
        }
        if itilcategories_id:
            payload["input"]["itilcategories_id"] = itilcategories_id
        if requesters_id:
            payload["input"]["_users_id_requester"] = requesters_id
        if assignees_ids:
            payload["input"]["_users_id_assign"] = list(assignees_ids)

        r = requests.post(
            f"{self.base_url}/Ticket",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        if r.status_code not in (200, 201):
            raise GlpiError(f"Crear ticket GLPI falló ({r.status_code}): {r.text[:400]}")
        return r.json()

    def upload_document(
        self, ticket_id: int, filepath: str, filename: str, display_name: str | None = None
    ) -> dict[str, Any]:
        """
        Sube un archivo a GLPI y lo vincula como documento del Ticket indicado.
        Usa multipart/form-data según la API REST de GLPI (endpoint /Document).
        filename: nombre de la parte multipart y del archivo en GLPI.
        display_name: nombre visible del documento en GLPI.
        """
        import json as _json

        display_name = display_name or filename
        document_meta = {
            "input": {
                "name": display_name,
                "_filename": [filename],
                "items_id": ticket_id,
                "itemtype": "Ticket",
            }
        }
        headers = self._headers()
        # Con multipart no se envía Content-Type manual; requests lo arma solo.
        headers.pop("Content-Type", None)

        with open(filepath, "rb") as fh:
            files = {
                "uploadManifest": (
                    None,
                    _json.dumps(document_meta),
                    "application/json",
                ),
                filename: (display_name, fh),
            }
            r = requests.post(
                f"{self.base_url}/Document",
                headers=headers,
                files=files,
                timeout=self.timeout,
            )
        if r.status_code not in (200, 201):
            raise GlpiError(f"Subir documento GLPI falló ({r.status_code}): {r.text[:400]}")
        return r.json()

    def add_followup(self, ticket_id: int, content: str) -> dict[str, Any]:
        payload = {
            "input": {
                "itemtype": "Ticket",
                "items_id": ticket_id,
                "content": content,
                "is_private": 0,
            }
        }
        r = requests.post(
            f"{self.base_url}/ITILFollowup",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        if r.status_code not in (200, 201):
            raise GlpiError(f"Followup GLPI falló ({r.status_code}): {r.text[:400]}")
        return r.json()

    def update_ticket_status(self, ticket_id: int, status: int) -> dict[str, Any]:
        """
        status GLPI típicos:
          1 nuevo, 2 en curso (asignado), 3 en curso (planificado),
          4 en espera, 5 resuelto, 6 cerrado
        """
        payload = {"input": {"id": ticket_id, "status": status}}
        r = requests.put(
            f"{self.base_url}/Ticket/{ticket_id}",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        if r.status_code not in (200, 201):
            raise GlpiError(f"Update ticket GLPI falló ({r.status_code}): {r.text[:400]}")
        return r.json()

    def update_ticket_content(self, ticket_id: int, name: str, content: str) -> dict[str, Any]:
        """Actualiza título y descripción de un ticket existente en GLPI."""
        payload = {"input": {"id": ticket_id, "name": name[:255], "content": content}}
        r = requests.put(
            f"{self.base_url}/Ticket/{ticket_id}",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        if r.status_code not in (200, 201):
            raise GlpiError(f"Update ticket GLPI falló ({r.status_code}): {r.text[:400]}")
        return r.json()

    def assign_technicians(
        self, ticket_id: int, glpi_user_ids: list[int]
    ) -> dict[str, Any]:
        """Asigna técnicos (usuarios GLPI) al ticket indicado."""
        payload = {
            "input": {
                "id": ticket_id,
                "_users_id_assign": [int(u) for u in glpi_user_ids],
            }
        }
        r = requests.put(
            f"{self.base_url}/Ticket/{ticket_id}",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        if r.status_code not in (200, 201):
            raise GlpiError(f"Asignar técnico en GLPI falló ({r.status_code}): {r.text[:400]}")
        return r.json()

    # ------------------------------------------------------------------
    #  Fotos de usuario (perfil)
    # ------------------------------------------------------------------

    def get_user_picture(self, glpi_id: int) -> bytes | None:
        """
        Descarga la foto de perfil de un usuario GLPI.
        Retorna los bytes de la imagen (PNG/JPG) o None si no tiene foto.
        """
        r = requests.get(
            f"{self.base_url}/User/{glpi_id}/Picture",
            headers=self._headers(),
            timeout=self.timeout,
        )
        if r.status_code == 200 and r.content and len(r.content) > 100:
            return r.content
        return None

    def upload_user_picture(
        self, glpi_id: int, filepath: str, filename: str
    ) -> dict[str, Any]:
        """
        Sube una foto de perfil a un usuario GLPI.
        Intenta múltiples approaches:
          1. POST multipart a /User/{id}/Picture (GLPI 10.0.7+)
          2. POST /Document + PUT /User con _picture (fallback)
        Retorna dict con info del resultado.
        """
        import json as _json

        resultado = {"ok": False, "metodo": "", "detalle": ""}

        # --- Approach 1: POST directo a /User/{id}/Picture ---
        try:
            headers = self._headers()
            headers.pop("Content-Type", None)
            with open(filepath, "rb") as fh:
                files = {"filename": (filename, fh)}
                r = requests.post(
                    f"{self.base_url}/User/{glpi_id}/Picture",
                    headers=headers,
                    files=files,
                    timeout=self.timeout,
                )
            if r.status_code in (200, 201):
                resultado["ok"] = True
                resultado["metodo"] = "directo"
                resultado["detalle"] = "Foto subida directamente al usuario"
                logger.info("Foto subida directa a GLPI usuario #%s", glpi_id)
                return resultado
        except (RequestException, OSError) as exc:
            logger.debug("Approach directo falló para GLPI #%s: %s", glpi_id, exc)

        # --- Approach 2: Document + vinculación ---
        try:
            display_name = f"avatar_{glpi_id}_{filename}"
            document_meta = {
                "input": {
                    "name": display_name,
                    "_filename": [filename],
                }
            }
            headers = self._headers()
            headers.pop("Content-Type", None)

            with open(filepath, "rb") as fh:
                files = {
                    "uploadManifest": (
                        None,
                        _json.dumps(document_meta),
                        "application/json",
                    ),
                    filename: (display_name, fh),
                }
                r = requests.post(
                    f"{self.base_url}/Document",
                    headers=headers,
                    files=files,
                    timeout=self.timeout,
                )
            if r.status_code not in (200, 201):
                resultado["detalle"] = f"Document falló ({r.status_code}): {r.text[:150]}"
                return resultado

            doc_data = r.json()
            doc_id = None
            if isinstance(doc_data, dict):
                doc_id = doc_data.get("id")
            elif isinstance(doc_data, list) and doc_data:
                doc_id = doc_data[0].get("id")

            if not doc_id:
                resultado["detalle"] = "GLPI no devolvió id del documento"
                return resultado

            # Intentar vincular con diferentes campos
            for campo in ("_picture", "picture"):
                payload = {"input": {"id": glpi_id, campo: [int(doc_id)]}}
                r2 = requests.put(
                    f"{self.base_url}/User/{glpi_id}",
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout,
                )
                if r2.status_code in (200, 201):
                    resultado["ok"] = True
                    resultado["metodo"] = "documento"
                    resultado["detalle"] = f"Foto subida como documento #{doc_id} y vinculada"
                    logger.info("Foto subida vía Document a GLPI usuario #%s, doc #%s", glpi_id, doc_id)
                    return resultado

            # Si la vinculación falló, al menos el documento quedó subido
            resultado["metodo"] = "documento_sin_vincular"
            resultado["detalle"] = f"Documento #{doc_id} subido pero no vinculado como foto de perfil"
            resultado["doc_id"] = int(doc_id)
            logger.warning(
                "Foto subida a GLPI usuario #%s como doc #%s pero sin vincular como perfil",
                glpi_id, doc_id,
            )
            return resultado

        except (RequestException, OSError) as exc:
            resultado["detalle"] = f"Error: {exc}"
            logger.warning("Error subiendo foto a GLPI usuario #%s: %s", glpi_id, exc)
            return resultado

    def update_user_profile(
        self,
        glpi_id: int,
        nombre: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> bool:
        """
        Actualiza campos de perfil de un usuario en GLPI.
        Retorna True si éxito.
        """
        input_data: dict[str, Any] = {"id": glpi_id}
        if nombre is not None:
            partes = nombre.split()
            input_data["firstname"] = " ".join(partes[:-1]) if len(partes) > 1 else nombre
            input_data["realname"] = partes[-1] if len(partes) > 1 else ""
        if phone is not None:
            input_data["phone"] = phone
        if email is not None:
            input_data["_useremails"] = [email]

        if len(input_data) <= 1:
            return True

        payload = {"input": input_data}
        r = requests.put(
            f"{self.base_url}/User/{glpi_id}",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        if r.status_code not in (200, 201):
            logger.warning(
                "Actualizar perfil GLPI #%s falló (%s): %s",
                glpi_id, r.status_code, r.text[:200],
            )
            return False
        return True


# Mapeo prioridad Dogger → urgency GLPI
PRIORITY_TO_URGENCY = {
    "baja": 2,
    "media": 3,
    "alta": 4,
    "urgente": 5,
}

# Mapeo estado Dogger → status GLPI
STATE_TO_GLPI_STATUS = {
    "abierto": 1,
    "en-progreso": 2,
    "resuelto": 5,
    "cerrado": 6,
}

# Mapeo inverso: status GLPI → estado Dogger (para el webhook)
GLPI_STATUS_TO_STATE = {
    1: "abierto",
    2: "en-progreso",
    3: "en-progreso",
    4: "en-progreso",
    5: "resuelto",
    6: "cerrado",
}

# Nombres legibles de status GLPI (para mostrar en el log de eventos)
GLPI_STATUS_NAMES = {
    1: "Nuevo",
    2: "En curso (asignado)",
    3: "En curso (planificado)",
    4: "En espera",
    5: "Resuelto",
    6: "Cerrado",
}


def _glpi_ids_asignados(ticket) -> list[int]:
    """IDs GLPI de los técnicos asignados al ticket (si los tienen configurado)."""
    tecnico = getattr(ticket, "tecnico_asignado", None)
    if tecnico and getattr(tecnico, "glpi_user_id", None):
        return [int(tecnico.glpi_user_id)]
    return []


def _contenido_ticket(ticket) -> str:
    from django.utils.html import escape

    descripcion = "<br>".join(escape(ticket.descripcion or "").splitlines())
    return (
        f"<p><b>Solicitante:</b> {escape(ticket.solicitante_nombre)}</p>"
        f"<p><b>Correo:</b> {escape(ticket.solicitante_email or '—')}</p>"
        f"<p><b>Punto:</b> {escape(ticket.solicitante_punto or '—')}</p>"
        f"<p><b>Código Dogger:</b> {ticket.codigo}</p>"
        f"<hr>{descripcion}"
    )


def sync_ticket_to_glpi(ticket) -> int | None:
    """
    Sincroniza un Ticket Dogger hacia GLPI si está habilitado.
    Guarda el id remoto en ticket.glpi_id (si el campo existe).
    Retorna el id GLPI, o None si GLPI no está habilitado/configurado.
    Lanza GlpiError si está habilitado pero la llamada falla.
    """
    client = GlpiClient()
    if not client.available:
        return None
    if getattr(ticket, "glpi_id", None):
        # Ya está en GLPI: no crear duplicado.
        return int(ticket.glpi_id)

    try:
        client.init_session()
        requester_id = None
        if ticket.solicitante_email:
            requester_id = client.find_user_by_email(ticket.solicitante_email)
        urgency = PRIORITY_TO_URGENCY.get(ticket.prioridad, 3)
        cat_glpi = None
        if ticket.categoria_id and getattr(ticket.categoria, "glpi_category_id", None):
            cat_glpi = ticket.categoria.glpi_category_id

        result = client.create_ticket(
            name=ticket.titulo,
            content=_contenido_ticket(ticket),
            urgency=urgency,
            itilcategories_id=cat_glpi,
            requesters_id=requester_id,
            assignees_ids=_glpi_ids_asignados(ticket),
        )
        # GLPI suele devolver {"id": N, "message": "..."}
        glpi_id = None
        if isinstance(result, dict):
            glpi_id = result.get("id")
            if glpi_id is None and isinstance(result.get("0"), dict):
                glpi_id = result["0"].get("id")
        if glpi_id and hasattr(ticket, "glpi_id"):
            ticket.glpi_id = int(glpi_id)
            ticket.save(update_fields=["glpi_id"])
        logger.info("Ticket %s sincronizado a GLPI id=%s", ticket.codigo, glpi_id)
        return int(glpi_id) if glpi_id else None
    except GlpiError:
        raise
    except requests.RequestException as exc:
        logger.exception("Error de conexión con GLPI para %s", ticket.codigo)
        raise GlpiError(f"sin conexión con GLPI ({exc.__class__.__name__})") from exc
    except Exception as exc:
        logger.exception("Error sync GLPI para %s: %s", ticket.codigo, exc)
        raise GlpiError(str(exc)) from exc
    finally:
        client.kill_session()


def sync_estado_to_glpi(ticket) -> bool:
    client = GlpiClient()
    if not client.available or not getattr(ticket, "glpi_id", None):
        return False
    status = STATE_TO_GLPI_STATUS.get(ticket.estado)
    if status is None:
        return False
    try:
        client.init_session()
        client.update_ticket_status(ticket.glpi_id, status)
        return True
    except requests.RequestException as exc:
        logger.exception("Error de conexión con GLPI (estado %s)", ticket.codigo)
        raise GlpiError(f"sin conexión con GLPI ({exc.__class__.__name__})") from exc
    except GlpiError:
        raise
    finally:
        client.kill_session()


def sync_followup_to_glpi(ticket, content: str) -> bool:
    client = GlpiClient()
    if not client.available or not getattr(ticket, "glpi_id", None) or not content.strip():
        return False
    try:
        client.init_session()
        client.add_followup(ticket.glpi_id, content.strip())
        return True
    except requests.RequestException as exc:
        logger.exception("Error de conexión con GLPI (followup %s)", ticket.codigo)
        raise GlpiError(f"sin conexión con GLPI ({exc.__class__.__name__})") from exc
    except GlpiError:
        raise
    finally:
        client.kill_session()


def sync_asignacion_to_glpi(ticket) -> bool:
    """
    Refleja el técnico asignado del ticket en GLPI.
    Requiere que el Usuario tenga glpi_user_id configurado (Django Admin).
    """
    ids = _glpi_ids_asignados(ticket)
    client = GlpiClient()
    if not client.available or not getattr(ticket, "glpi_id", None) or not ids:
        return False
    try:
        client.init_session()
        client.assign_technicians(ticket.glpi_id, ids)
        return True
    except requests.RequestException as exc:
        logger.exception("Error de conexión con GLPI (asignación %s)", ticket.codigo)
        raise GlpiError(f"sin conexión con GLPI ({exc.__class__.__name__})") from exc
    except GlpiError:
        raise
    finally:
        client.kill_session()


def sync_edicion_to_glpi(ticket) -> bool:
    """Actualiza en GLPI título y descripción tras una edición local."""
    client = GlpiClient()
    if not client.available or not getattr(ticket, "glpi_id", None):
        return False
    try:
        client.init_session()
        client.update_ticket_content(
            ticket.glpi_id, ticket.titulo, _contenido_ticket(ticket)
        )
        return True
    except requests.RequestException as exc:
        logger.exception("Error de conexión con GLPI (edición %s)", ticket.codigo)
        raise GlpiError(f"sin conexión con GLPI ({exc.__class__.__name__})") from exc
    except GlpiError:
        raise
    finally:
        client.kill_session()


def sync_adjuntos_to_glpi(ticket) -> int:
    """
    Sube todos los TicketAdjunto de un ticket (que aún no se hayan sincronizado)
    al ticket correspondiente en GLPI. Requiere que ticket.glpi_id ya exista
    (es decir, que sync_ticket_to_glpi se haya ejecutado antes).
    Retorna la cantidad de archivos subidos exitosamente.
    """
    client = GlpiClient()
    if not client.available or not getattr(ticket, "glpi_id", None):
        return 0

    adjuntos = list(ticket.adjuntos.filter(sincronizado_glpi=False))
    if not adjuntos:
        return 0

    subidos = 0
    try:
        client.init_session()
        for adjunto in adjuntos:
            try:
                filepath = adjunto.archivo.path
                filename = posixpath.basename(adjunto.archivo.name.replace("\\", "/"))
                client.upload_document(
                    ticket.glpi_id,
                    filepath,
                    filename,
                    display_name=adjunto.nombre_original,
                )
                adjunto.sincronizado_glpi = True
                adjunto.save(update_fields=["sincronizado_glpi"])
                subidos += 1
            except Exception as exc:
                logger.exception(
                    "Error subiendo adjunto %s del ticket %s a GLPI: %s",
                    adjunto.pk, ticket.codigo, exc,
                )
        return subidos
    except requests.RequestException as exc:
        raise GlpiError(f"sin conexión con GLPI ({exc.__class__.__name__})") from exc
    finally:
        client.kill_session()


def sync_avatar_to_glpi(usuario) -> dict:
    """
    Sube el avatar local de un usuario a GLPI.
    Retorna dict con {ok, metodo, detalle}.
    """
    if not usuario.avatar:
        return {"ok": False, "detalle": "Sin foto de perfil local"}
    if not getattr(usuario, "glpi_user_id", None):
        return {"ok": False, "detalle": "Usuario no vinculado a GLPI"}
    client = GlpiClient()
    if not client.available:
        return {"ok": False, "detalle": "GLPI no configurado"}
    try:
        client.init_session()
        filepath = usuario.avatar.path
        import posixpath
        filename = posixpath.basename(usuario.avatar.name.replace("\\", "/"))
        return client.upload_user_picture(int(usuario.glpi_user_id), filepath, filename)
    except Exception as exc:
        logger.warning("sync_avatar_to_glpi user=%s: %s", usuario.pk, exc)
        return {"ok": False, "detalle": str(exc)}
    finally:
        client.kill_session()


def sync_avatar_from_glpi(usuario) -> bool:
    """
    Descarga la foto de perfil de GLPI y la guarda como avatar local.
    Retorna True si se descargó una foto nueva.
    """
    if not getattr(usuario, "glpi_user_id", None):
        return False
    client = GlpiClient()
    if not client.available:
        return False
    try:
        client.init_session()
        image_bytes = client.get_user_picture(int(usuario.glpi_user_id))
        if not image_bytes:
            return False
        # Guardar imagen
        from django.core.files.base import ContentFile
        ext = ".png"
        if image_bytes[:3] == b'\xff\xd8\xff':
            ext = ".jpg"
        elif image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            ext = ".png"
        elif image_bytes[:4] == b'RIFF':
            ext = ".webp"
        nombre_archivo = f"avatar_glpi_{usuario.pk}{ext}"
        usuario.avatar.save(nombre_archivo, ContentFile(image_bytes), save=True)
        logger.info("Avatar descargado de GLPI para usuario %s", usuario.pk)
        return True
    except Exception as exc:
        logger.warning("sync_avatar_from_glpi user=%s: %s", usuario.pk, exc)
        return False
    finally:
        client.kill_session()


def sync_perfil_to_glpi(usuario) -> bool:
    """
    Actualiza nombre, email y teléfono de un usuario en GLPI.
    Retorna True si éxito.
    """
    if not getattr(usuario, "glpi_user_id", None):
        return False
    client = GlpiClient()
    if not client.available:
        return False
    try:
        client.init_session()
        return client.update_user_profile(
            glpi_id=int(usuario.glpi_user_id),
            nombre=usuario.nombre,
            email=usuario.email,
            phone=getattr(usuario, "telefono", "") or "",
        )
    except Exception as exc:
        logger.warning("sync_perfil_to_glpi user=%s: %s", usuario.pk, exc)
        return False
    finally:
        client.kill_session()


def sync_perfil_from_glpi(usuario) -> bool:
    """
    Actualiza nombre y email de un usuario local desde GLPI.
    Retorna True si hubo cambios.
    """
    if not getattr(usuario, "glpi_user_id", None):
        return False
    client = GlpiClient()
    if not client.available:
        return False
    try:
        client.init_session()
        # Obtener datos del usuario específico
        r = requests.get(
            f"{client.base_url}/User/{usuario.glpi_user_id}",
            headers=client._headers(),
            timeout=client.timeout,
        )
        if r.status_code != 200:
            return False
        data = r.json()
        if not isinstance(data, dict):
            return False

        cambios = False
        glpi_firstname = (data.get("firstname") or "").strip()
        glpi_realname = (data.get("realname") or "").strip()
        glpi_nombre = f"{glpi_firstname} {glpi_realname}".strip()
        glpi_phone = (data.get("phone") or "").strip()

        if glpi_nombre and glpi_nombre != usuario.nombre:
            usuario.nombre = glpi_nombre
            cambios = True
        if glpi_phone and glpi_phone != getattr(usuario, "telefono", ""):
            usuario.telefono = glpi_phone
            cambios = True
        if cambios:
            usuario.save(update_fields=["nombre", "telefono"])
        return cambios
    except Exception as exc:
        logger.warning("sync_perfil_from_glpi user=%s: %s", usuario.pk, exc)
        return False
    finally:
        client.kill_session()
