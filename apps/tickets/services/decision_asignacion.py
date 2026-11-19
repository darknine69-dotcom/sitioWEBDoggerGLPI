"""Cálculo puro de candidatos para el futuro motor transaccional.

No consulta ni modifica la base de datos; el llamador debe proporcionar una
instantánea coherente y persistir la decisión y la rotación atómicamente.
"""
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional


PESOS_INICIALES = {"urgente": 5, "alta": 3, "media": 2, "baja": 1}


@dataclass(frozen=True)
class Candidato:
    pk: int
    carga: int
    capacidad: int
    orden_rotacion: int = 0
    predeterminado: bool = False

    def __post_init__(self):
        if self.carga < 0 or self.capacidad <= 0 or self.orden_rotacion < 0:
            raise ValueError("La carga y la rotación deben ser no negativas y la capacidad positiva.")


@dataclass(frozen=True)
class Decision:
    candidato: Optional[Candidato]
    motivo: str


def elegir_candidato(candidatos, prioridad, pesos=None, margen_puntos=20):
    """Elige sin efectos secundarios; margen se expresa en puntos porcentuales."""
    pesos = PESOS_INICIALES if pesos is None else pesos
    if prioridad not in PESOS_INICIALES or any(
        clave not in pesos or not isinstance(pesos[clave], int) or isinstance(pesos[clave], bool) or pesos[clave] <= 0
        for clave in PESOS_INICIALES
    ):
        raise ValueError("Prioridad o pesos inválidos.")
    if not isinstance(margen_puntos, int) or isinstance(margen_puntos, bool) or not 0 <= margen_puntos <= 100:
        raise ValueError("El margen debe estar entre 0 y 100 puntos porcentuales.")
    candidatos = list(candidatos)
    if not candidatos:
        return Decision(None, "sin_candidatos")
    disponibles = [c for c in candidatos if c.carga + pesos[prioridad] <= c.capacidad]
    if not disponibles:
        return Decision(None, "capacidad_insuficiente")

    def ocupacion(c):
        return Fraction(c.carga, c.capacidad)

    minimo = min(ocupacion(c) for c in disponibles)
    empatados = [c for c in disponibles if ocupacion(c) == minimo]
    if prioridad in ("urgente", "alta"):
        predeterminados = [c for c in empatados if c.predeterminado]
        if predeterminados:
            empatados = predeterminados
    else:
        preferidos = [c for c in disponibles if c.predeterminado and ocupacion(c) - minimo <= Fraction(margen_puntos, 100)]
        if preferidos:
            return Decision(min(preferidos, key=lambda c: (c.orden_rotacion, c.pk)), "preferencia_categoria")
    return Decision(min(empatados, key=lambda c: (c.orden_rotacion, c.pk)), "menor_ocupacion")
