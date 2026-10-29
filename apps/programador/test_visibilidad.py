from types import SimpleNamespace

from django.test import SimpleTestCase

from .models import CalendarioEvento
from .views import _puede_ver_evento


class VisibilidadEventosTests(SimpleTestCase):
    def usuario(self, pk, rol="tecnico"):
        return SimpleNamespace(pk=pk, rol=rol)

    def evento(self, visibilidad, tecnico_id=2, creado_por_id=1, tipo=CalendarioEvento.Tipo.RECORDATORIO):
        return SimpleNamespace(
            tipo=tipo, tecnico_id=tecnico_id, creado_por_id=creado_por_id,
            metadatos={"visibilidad": visibilidad} if visibilidad else {},
        )

    def test_persona_limita_a_destinatario_y_creador(self):
        evento = self.evento("persona")
        self.assertTrue(_puede_ver_evento(self.usuario(1), evento))
        self.assertTrue(_puede_ver_evento(self.usuario(2), evento))
        self.assertFalse(_puede_ver_evento(self.usuario(3), evento))
        self.assertTrue(_puede_ver_evento(self.usuario(3, "admin"), evento))

    def test_todos_comparte_con_el_equipo(self):
        evento = self.evento("todos", tecnico_id=None)
        self.assertTrue(_puede_ver_evento(self.usuario(3), evento))
        self.assertFalse(_puede_ver_evento(self.usuario(4, "usuario"), evento))

    def test_registros_anteriores_mantienen_su_alcance(self):
        self.assertFalse(_puede_ver_evento(self.usuario(3), self.evento(None)))
        self.assertTrue(_puede_ver_evento(self.usuario(3), self.evento(None, tipo=CalendarioEvento.Tipo.PROYECTO)))
