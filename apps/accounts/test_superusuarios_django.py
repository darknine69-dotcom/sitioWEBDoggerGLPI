from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class GestionSuperusuariosTests(TestCase):
    def setUp(self):
        usuarios = get_user_model().objects
        self.root = usuarios.create_user("root@test.com", "Root", "clave-segura", rol="admin", is_superuser=True, is_staff=True)
        self.admin = usuarios.create_user("admin@test.com", "Admin", "clave", rol="admin")
        self.tecnico = usuarios.create_user("tecnico@test.com", "Técnico", "clave", rol="tecnico")
        self.url = reverse("accounts:gestionar_superusuario")

    def enviar(self, cuenta, accion="conceder", clave="clave-segura"):
        return self.client.post(self.url, {"usuario": cuenta.pk, "accion": accion, "confirmar_password": clave})

    def test_superusuario_puede_conceder_y_retirar_con_auditoria(self):
        self.client.force_login(self.root)
        self.assertEqual(self.enviar(self.admin).status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)
        self.assertTrue(self.admin.is_staff)
        self.assertEqual(self.enviar(self.admin, "retirar").status_code, 302)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_superuser)
        self.assertEqual(LogEntry.objects.filter(user_id=self.root.pk, object_id=str(self.admin.pk)).count(), 2)

    def test_solo_superusuario_ve_controles_y_puede_modificar(self):
        for usuario in (self.admin, self.tecnico):
            with self.subTest(rol=usuario.rol):
                self.client.force_login(usuario)
                self.assertNotContains(self.client.get(reverse("accounts:ajustes")), reverse("accounts:gestionar_superusuario"))
                self.assertEqual(self.enviar(self.admin).status_code, 403)
        self.client.force_login(self.root)
        respuesta = self.client.get(reverse("accounts:ajustes"))
        self.assertContains(respuesta, reverse("accounts:gestionar_superusuario"))
        self.assertContains(respuesta, reverse("admin:index"))

    def test_clave_incorrecta_no_cambia_permisos(self):
        self.client.force_login(self.root)
        self.enviar(self.admin, clave="incorrecta")
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_superuser)

    def test_lista_administradores_por_rol_base_y_no_por_vista_temporal(self):
        self.admin.rol_base = "admin"
        self.admin.rol = "tecnico"
        self.admin.save(update_fields=["rol_base", "rol"])
        self.tecnico.rol_base = "tecnico"
        self.tecnico.rol = "admin"
        self.tecnico.save(update_fields=["rol_base", "rol"])
        self.client.force_login(self.root)
        respuesta = self.client.get(reverse("accounts:ajustes"))
        self.assertContains(respuesta, self.admin.email)
        self.assertNotContains(respuesta, f'{self.tecnico.nombre} · {self.tecnico.email} · Sin acceso total')
        self.assertEqual(self.enviar(self.tecnico).status_code, 403)
        self.assertEqual(self.enviar(self.admin).status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)

    def test_no_concede_a_tecnico_inactivo_ni_se_retira_a_si_mismo(self):
        self.client.force_login(self.root)
        self.assertEqual(self.enviar(self.tecnico).status_code, 403)
        self.admin.activo = False
        self.admin.save(update_fields=["activo"])
        self.assertEqual(self.enviar(self.admin).status_code, 403)
        self.assertEqual(self.enviar(self.root, "retirar").status_code, 403)
        self.root.refresh_from_db()
        self.assertTrue(self.root.is_superuser)

    def test_solo_post_y_actor_activo(self):
        self.client.force_login(self.root)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.root.activo = False
        self.root.save(update_fields=["activo"])
        self.assertEqual(self.enviar(self.admin).status_code, 403)
