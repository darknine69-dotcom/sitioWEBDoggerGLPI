from django.template.loader import render_to_string
from django.test import TestCase

from apps.accounts.models import Usuario
from apps.tickets.views import _tecnicos_resumen


class RolActualTecnicosTest(TestCase):
    def test_rol_actual_visible_solo_con_permiso_y_conserva_rol_base(self):
        Usuario.objects.create_user(
            email="cambio@example.com", password="x", nombre="Cambio",
            rol=Usuario.Rol.OBSERVADOR, rol_base=Usuario.Rol.TECNICO,
            cambio_rol_habilitado=True,
        )
        Usuario.objects.create_user(
            email="normal@example.com", password="x", nombre="Normal",
            rol=Usuario.Rol.TECNICO,
        )
        resumen = _tecnicos_resumen([])
        html = render_to_string("tickets/_dashboard_tecnicos_rows.html", {"tecnicos_stats": resumen})
        self.assertEqual(len(resumen), 2)
        self.assertEqual(html.count('class="tec-role-badge"'), 2)
        self.assertIn('title="Rol base: Técnico"', html)
        self.assertIn('title="Rol actual: Observador"', html)

    def test_mismo_rol_solo_muestra_base(self):
        Usuario.objects.create_user(
            email="base@example.com", password="x", nombre="Base",
            rol=Usuario.Rol.TECNICO, rol_base=Usuario.Rol.TECNICO,
            cambio_rol_habilitado=True,
        )
        html = render_to_string("tickets/_dashboard_tecnicos_rows.html", {"tecnicos_stats": _tecnicos_resumen([])})
        self.assertEqual(html.count('class="tec-role-badge"'), 1)
        self.assertIn('title="Rol base: Técnico"', html)
