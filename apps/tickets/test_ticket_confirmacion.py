from django.test import TestCase
from django.urls import reverse


class ConfirmacionTicketTest(TestCase):
    def _ver_confirmacion(self, tecnico):
        sesion = self.client.session
        sesion["ticket_creado_info"] = {
            "codigo": "DG-EN-0053", "titulo": "Sin red", "categoria": "Red",
            "prioridad": "urgente", "prioridad_label": "Urgente",
            "tecnico_nombre": tecnico, "tecnico_iniciales": "TE",
        }
        sesion.save()
        return self.client.get(reverse("tickets:portal"))

    def test_informa_cuando_sigue_sin_tecnico(self):
        respuesta = self._ver_confirmacion("")
        self.assertContains(respuesta, "Pendiente de asignación")
        self.assertContains(respuesta, "aún no tiene un técnico asignado")
        self.assertNotContains(respuesta, "ya tiene un técnico asignado")

    def test_informa_cuando_ya_hay_tecnico(self):
        respuesta = self._ver_confirmacion("Técnico")
        self.assertContains(respuesta, "ya tiene un técnico asignado")
        self.assertNotContains(respuesta, "Pendiente de asignación")
