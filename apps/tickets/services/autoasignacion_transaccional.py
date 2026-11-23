"""Asignación opt-in: requiere configuración y perfiles explícitos."""
from contextlib import contextmanager
from functools import wraps
import logging
from django.contrib.auth import get_user_model
from django.db import connections, transaction
from django.db.models import Count
from django.utils import timezone

from apps.notificaciones.models import AlertaOperativa, HistorialAlerta
from apps.tickets.models import ConfiguracionAutoasignacion, DecisionAutoasignacion, PerfilAutoasignacion, Ticket
from apps.tickets.services.decision_asignacion import Candidato, elegir_candidato

logger = logging.getLogger(__name__)


def _avisar_administradores(ticket_id, motivo):
    """Entrega en campana con la misma clave del aviso existente de alta."""
    from django.urls import reverse
    from apps.notificaciones.models import Notificacion
    from apps.notificaciones.services import crear

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
        if ticket.tecnico_asignado_id:
            return
        detalle = "No hay técnicos elegibles" if motivo == "sin_candidatos" else "No hay capacidad disponible"
        for usuario in get_user_model().objects.filter(rol="admin", activo=True, is_active=True):
            crear(usuario, Notificacion.Tipo.TICKET_NUEVO, f"Ticket sin asignar {ticket.codigo}",
                  f"{detalle} · {ticket.titulo[:80]}", url=reverse("tickets:sin_asignar"),
                  clave=f"ticket:{ticket.pk}:nuevo:{usuario.pk}")
    except Exception:
        # La alerta operativa queda persistida aunque falle la entrega.
        logger.exception("No se pudo entregar la alerta del ticket %s", ticket_id)


class BloqueoAsignacionNoDisponible(RuntimeError):
    pass


@contextmanager
def coordinacion_asignacion(*, using="default"):
    """Orden común de bloqueos: configuración global y luego tickets.

    La fila única debe existir antes de activar el motor. El bloqueo de SQLite
    no sirve como prueba de serialización entre procesos.
    """
    with transaction.atomic(using=using):
        ConfiguracionAutoasignacion.objects.using(using).select_for_update().filter(pk=1).first()
        yield


def escritura_coordinada(funcion):
    """Protege escrituras que alteran reglas o elegibilidad del motor."""
    @wraps(funcion)
    def envuelta(*args, **kwargs):
        with coordinacion_asignacion():
            return funcion(*args, **kwargs)
    return envuelta


def asignar_manual(ticket_id, tecnico, *, solo_sin_asignar=False, cambiar_tecnico=True, using="default", cambios=None):
    """Aplica la decisión manual después de releer el ticket bajo bloqueo."""
    with coordinacion_asignacion(using=using):
        ticket = Ticket.objects.using(using).select_for_update().get(pk=ticket_id)
        if solo_sin_asignar and ticket.tecnico_asignado_id:
            return ticket, False
        for campo, valor in (cambios or {}).items():
            if campo not in ("solicitante_punto", "categoria"):
                raise ValueError("Campo no permitido en asignación manual")
            setattr(ticket, campo, valor)
        campos = ["fecha_actualizacion", *(cambios or {}).keys()]
        if cambiar_tecnico:
            ticket.tecnico_asignado = tecnico
            ticket.asignacion_automatica = False
            ticket.asignacion_manual_protegida = True
            campos.extend(["tecnico_asignado", "asignacion_automatica", "asignacion_manual_protegida"])
        ticket.save(using=using, update_fields=campos)
        if cambiar_tecnico and tecnico:
            alerta = AlertaOperativa.objects.using(using).select_for_update().filter(
                clave_origen=f"autoasignacion:ticket:{ticket.pk}"
            ).first()
            if alerta and alerta.estado != AlertaOperativa.Estado.RESUELTA:
                alerta.estado = AlertaOperativa.Estado.RESUELTA
                alerta.resuelta_en = timezone.now()
                alerta.save(using=using, update_fields=["estado", "resuelta_en"])
                HistorialAlerta.objects.using(using).create(alerta=alerta, accion="resuelta", detalle="Asignación manual realizada")
        return ticket, True


def asignar_ticket(ticket_id, *, using="default"):
    """Decide y guarda conjuntamente; no ejecuta integraciones externas."""
    conexion = connections[using]
    if not conexion.features.has_select_for_update:
        if not ConfiguracionAutoasignacion.objects.using(using).filter(pk=1, activa=True).exists():
            logger.info("Motor de autoasignación desactivado para ticket %s", ticket_id)
            return None
        raise BloqueoAsignacionNoDisponible("El backend no ofrece select_for_update; no se asignó el ticket.")
    with transaction.atomic(using=using):
        # Fila única preconfigurada: nunca crearla durante una decisión.
        config = ConfiguracionAutoasignacion.objects.using(using).select_for_update().filter(pk=1).first()
        if not config or not config.activa:
            logger.info("Motor de autoasignación desactivado para ticket %s", ticket_id)
            return None
        ticket = Ticket.objects.using(using).select_for_update().get(pk=ticket_id)
        if ticket.tecnico_asignado_id or ticket.asignacion_manual_protegida or not ticket.categoria_id or not ticket.categoria.activo or ticket.estado not in (Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO):
            return None
        perfiles = list(PerfilAutoasignacion.objects.using(using).select_related("tecnico").prefetch_related("categorias", "puntos_cobertura", "cuentas_cobertura").filter(
            habilitado=True, tecnico__activo=True, tecnico__is_active=True,
            tecnico__rol__in=("tecnico", "admin"),
        ).order_by("tecnico_id"))
        perfiles = [p for p in perfiles if not p.categorias.all() or any(c.pk == ticket.categoria_id for c in p.categorias.all())]
        punto_ticket = (ticket.solicitante_punto or "").strip().casefold()
        correo_ticket = (ticket.solicitante_email or "").strip().casefold()
        perfiles = [p for p in perfiles if p.cobertura_general or any(
            punto.activo and punto.nombre.strip().casefold() == punto_ticket for punto in p.puntos_cobertura.all()
        ) or any(cuenta.activo and cuenta.is_active and cuenta.rol == "usuario" and correo_ticket and cuenta.email.strip().casefold() == correo_ticket for cuenta in p.cuentas_cobertura.all())]
        pesos = {"urgente": config.peso_urgente, "alta": config.peso_alta, "media": config.peso_media, "baja": config.peso_baja}
        cargas = {p.tecnico_id: 0 for p in perfiles}
        filas = Ticket.objects.using(using).filter(
            tecnico_asignado_id__in=cargas, estado__in=(Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO),
        ).values("tecnico_asignado_id", "prioridad").annotate(total=Count("id"))
        for fila in filas:
            if fila["prioridad"] not in pesos:
                raise ValueError("No se puede determinar la carga de una prioridad desconocida.")
            cargas[fila["tecnico_asignado_id"]] += fila["total"] * pesos[fila["prioridad"]]
        candidatos = [Candidato(p.tecnico_id, cargas[p.tecnico_id], p.capacidad, p.orden_rotacion,
                                p.tecnico_id == ticket.categoria.tecnico_default_id) for p in perfiles]
        decision = elegir_candidato(candidatos, ticket.prioridad, pesos, config.margen_puntos)
        logger.info("Decisión de autoasignación ticket=%s motivo=%s", ticket.pk, decision.motivo)
        elegido = decision.candidato
        if elegido:
            ticket.tecnico_asignado_id = elegido.pk
            ticket.asignacion_automatica = True
            ticket.save(using=using, update_fields=["tecnico_asignado", "asignacion_automatica"])
            config.secuencia += 1
            config.save(using=using, update_fields=["secuencia"])
            PerfilAutoasignacion.objects.using(using).filter(tecnico_id=elegido.pk).update(orden_rotacion=config.secuencia)
        DecisionAutoasignacion.objects.using(using).create(
            ticket=ticket, tecnico_id=elegido.pk if elegido else None, motivo=decision.motivo,
            carga=elegido.carga if elegido else None, capacidad=elegido.capacidad if elegido else None,
            prioridad=ticket.prioridad, categoria_nombre=str(ticket.categoria),
        )
        clave_alerta = f"autoasignacion:ticket:{ticket.pk}"
        if not elegido:
            alerta, creada = AlertaOperativa.objects.using(using).get_or_create(
                clave_origen=clave_alerta,
                defaults={"ticket": ticket, "tipo": "asignacion_pendiente", "codigo_ticket": ticket.codigo,
                          "titulo_ticket": (ticket.titulo or "")[:200]},
            )
            if creada:
                HistorialAlerta.objects.using(using).create(alerta=alerta, accion="creada", detalle=decision.motivo)
            elif alerta.estado == AlertaOperativa.Estado.RESUELTA:
                alerta.estado = AlertaOperativa.Estado.ABIERTA
                alerta.resuelta_en = None
                alerta.save(using=using, update_fields=["estado", "resuelta_en"])
                HistorialAlerta.objects.using(using).create(alerta=alerta, accion="reabierta", detalle=decision.motivo)
            if using == "default":
                transaction.on_commit(lambda: _avisar_administradores(ticket.pk, decision.motivo), using=using)
        else:
            alerta = AlertaOperativa.objects.using(using).select_for_update().filter(clave_origen=clave_alerta).first()
            if alerta and alerta.estado != AlertaOperativa.Estado.RESUELTA:
                alerta.estado = AlertaOperativa.Estado.RESUELTA
                alerta.resuelta_en = timezone.now()
                alerta.save(using=using, update_fields=["estado", "resuelta_en"])
                HistorialAlerta.objects.using(using).create(alerta=alerta, accion="resuelta", detalle="Asignación automática realizada")
        return decision
