from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.db import connection
from unittest.mock import patch

from apps.tickets.models import Categoria, ConfiguracionAutoasignacion, PerfilAutoasignacion, Punto, Ticket
from apps.tickets.services.autoasignacion_transaccional import asignar_ticket


class PantallaAutoasignacionTests(TestCase):
    def setUp(self):
        usuarios = get_user_model().objects
        self.superusuario = usuarios.create_user("root@example.com", "Root", "clave", rol="admin", is_superuser=True, is_staff=True)
        self.admin = usuarios.create_user("admin@example.com", "Admin", "clave", rol="admin")
        self.tecnico = usuarios.create_user("tec@example.com", "Técnico", "clave", rol="tecnico")
        self.categoria = Categoria.objects.create(grupo="TI", nombre="Red")
        self.punto = Punto.objects.create(nombre="Norte")
        self.url = reverse("tickets:configuracion_autoasignacion")

    def test_solo_superusuario_accede(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(self.superusuario)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_muestra_miga_de_pan_de_configuracion(self):
        self.client.force_login(self.superusuario)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'aria-label="Ruta de navegación"')
        self.assertEqual(respuesta.context["encabezado"]["actual"], "Asignación automática")
        self.assertEqual(respuesta.context["encabezado"]["padres"][0]["url"], reverse("accounts:ajustes"))

    def test_reglas_no_permiten_activar_motor(self):
        self.client.force_login(self.superusuario)
        respuesta = self.client.post(self.url, {"accion": "reglas", "peso_urgente": 5, "peso_alta": 3, "peso_media": 2, "peso_baja": 1, "margen_puntos": 20, "activa": "on"})
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(ConfiguracionAutoasignacion.objects.get(pk=1).activa)

    def test_motor_se_puede_desactivar(self):
        self.client.force_login(self.superusuario)
        ConfiguracionAutoasignacion.objects.create(pk=1, activa=True)
        self.assertEqual(self.client.post(self.url, {"accion": "desactivar"}).status_code, 302)
        self.assertFalse(ConfiguracionAutoasignacion.objects.get(pk=1).activa)

    def test_puede_deshabilitar_perfil_de_tecnico_inactivo(self):
        self.client.force_login(self.superusuario)
        perfil = PerfilAutoasignacion.objects.create(tecnico=self.tecnico, habilitado=True, cobertura_general=True, capacidad=10)
        self.tecnico.activo = False
        self.tecnico.is_active = False
        self.tecnico.save(update_fields=["activo", "is_active"])
        respuesta = self.client.post(self.url, {"accion": "perfil", "tecnico": self.tecnico.pk, "capacidad": 10, "cobertura_general": "on"})
        self.assertEqual(respuesta.status_code, 302)
        perfil.refresh_from_db()
        self.assertFalse(perfil.habilitado)

    def test_no_puede_habilitar_perfil_de_cuenta_inactiva(self):
        self.client.force_login(self.superusuario)
        perfil = PerfilAutoasignacion.objects.create(tecnico=self.tecnico, habilitado=False, cobertura_general=True, capacidad=10)
        self.tecnico.activo = False
        self.tecnico.is_active = False
        self.tecnico.save(update_fields=["activo", "is_active"])
        respuesta = self.client.post(self.url, {"accion": "perfil", "tecnico": self.tecnico.pk, "capacidad": 10, "cobertura_general": "on", "habilitado": "on"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "La cuenta debe estar activa")
        perfil.refresh_from_db()
        self.assertFalse(perfil.habilitado)

    def test_editar_perfil_conserva_especialidad_inactiva_seleccionada(self):
        self.client.force_login(self.superusuario)
        perfil = PerfilAutoasignacion.objects.create(tecnico=self.tecnico, habilitado=True, cobertura_general=True, capacidad=10)
        perfil.categorias.add(self.categoria)
        self.categoria.activo = False
        self.categoria.save(update_fields=["activo"])
        respuesta = self.client.post(self.url, {"accion": "perfil", "tecnico": self.tecnico.pk, "capacidad": 10, "cobertura_general": "on", "habilitado": "on", "categorias": [self.categoria.pk]})
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(perfil.categorias.filter(pk=self.categoria.pk).exists())

    def test_cobertura_restringida_exige_punto_activo(self):
        self.client.force_login(self.superusuario)
        perfil = PerfilAutoasignacion.objects.create(tecnico=self.tecnico, habilitado=False, cobertura_general=False, capacidad=10)
        perfil.puntos_cobertura.add(self.punto)
        self.punto.activo = False
        self.punto.save(update_fields=["activo"])
        respuesta = self.client.post(self.url, {"accion": "perfil", "tecnico": self.tecnico.pk, "capacidad": 10, "habilitado": "on", "puntos_cobertura": [self.punto.pk]})
        self.assertEqual(respuesta.status_code, 200)
        perfil.refresh_from_db()
        self.assertFalse(perfil.habilitado)

    def test_activar_exige_backend_con_bloqueo(self):
        self.client.force_login(self.superusuario)
        with patch.object(connection.features, "has_select_for_update", False):
            self.assertEqual(self.client.post(self.url, {"accion": "activar"}).status_code, 302)
        self.assertFalse(ConfiguracionAutoasignacion.objects.filter(pk=1, activa=True).exists())

    def test_superusuario_puede_activar_y_desactivar(self):
        self.client.force_login(self.superusuario)
        # Solo simula la capacidad de bloqueo; SQLite no valida concurrencia.
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            self.assertEqual(self.client.post(self.url, {"accion": "activar"}).status_code, 302)
        self.assertTrue(ConfiguracionAutoasignacion.objects.get(pk=1).activa)
        self.client.post(self.url, {"accion": "desactivar"})
        self.assertFalse(ConfiguracionAutoasignacion.objects.get(pk=1).activa)

    def test_rechaza_capacidad_y_cobertura_incompletas(self):
        self.client.force_login(self.superusuario)
        respuesta = self.client.post(self.url, {"accion": "perfil", "tecnico": self.tecnico.pk, "habilitado": "on", "capacidad": 0})
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(PerfilAutoasignacion.objects.exists())
        self.assertContains(respuesta, "Selecciona puntos")

    def test_crea_y_actualiza_perfil_restringido(self):
        self.client.force_login(self.superusuario)
        datos = {"accion": "perfil", "tecnico": self.tecnico.pk, "habilitado": "on", "capacidad": 10, "puntos_cobertura": [self.punto.pk], "categorias": [self.categoria.pk]}
        self.assertEqual(self.client.post(self.url, datos).status_code, 302)
        datos["capacidad"] = 15
        self.assertEqual(self.client.post(self.url, datos).status_code, 302)
        perfil = PerfilAutoasignacion.objects.get(tecnico=self.tecnico)
        self.assertEqual(perfil.capacidad, 15)
        self.assertEqual(list(perfil.puntos_cobertura.all()), [self.punto])
        self.assertEqual(list(perfil.categorias.all()), [self.categoria])

    def test_lista_direcciones_y_guarda_cobertura_por_cuenta(self):
        cuenta = get_user_model().objects.create_user("pdv@example.com", "Sede Norte", "clave", rol="usuario", ubicacion="Calle 25")
        self.client.force_login(self.superusuario)
        respuesta = self.client.get(self.url)
        for dato in ("Sede Norte", "Calle 25", "pdv@example.com"):
            self.assertContains(respuesta, dato)
        respuesta = self.client.post(self.url, {"accion": "perfil", "tecnico": self.tecnico.pk, "habilitado": "on", "capacidad": 20, "cuentas_cobertura": [cuenta.pk], "categorias": [self.categoria.pk]})
        self.assertEqual(respuesta.status_code, 302)
        perfil = PerfilAutoasignacion.objects.get(tecnico=self.tecnico)
        self.assertEqual(list(perfil.cuentas_cobertura.all()), [cuenta])
        self.assertEqual(list(perfil.categorias.all()), [self.categoria])
        respuesta = self.client.get(self.url, {"tecnico": self.tecnico.pk})
        self.assertContains(respuesta, f'name="cuentas_cobertura" value="{cuenta.pk}" checked')

    def test_cuentas_mantienen_seleccion_si_formulario_es_invalido(self):
        cuenta = get_user_model().objects.create_user("pdv@example.com", "Sede Norte", "clave", rol="usuario", ubicacion="Calle 25")
        self.client.force_login(self.superusuario)
        respuesta = self.client.post(self.url, {"accion": "perfil", "tecnico": self.tecnico.pk, "habilitado": "on", "capacidad": 0, "cuentas_cobertura": [cuenta.pk]})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, f'name="cuentas_cobertura" value="{cuenta.pk}" checked')

    def test_panel_muestra_cobertura_y_carga_ponderada(self):
        self.client.force_login(self.superusuario)
        ConfiguracionAutoasignacion.objects.create(pk=1, peso_urgente=5, peso_alta=3)
        perfil = PerfilAutoasignacion.objects.create(tecnico=self.tecnico, habilitado=True, capacidad=20)
        perfil.puntos_cobertura.add(self.punto)
        Ticket.objects.create(titulo="Fallo de red", categoria=self.categoria, prioridad="urgente", tecnico_asignado=self.tecnico)
        Ticket.objects.create(titulo="Otro fallo", categoria=self.categoria, prioridad="alta", tecnico_asignado=self.tecnico)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Norte")
        self.assertEqual(respuesta.context["perfiles"][0].carga_actual, 8)
        self.assertEqual(respuesta.context["perfiles"][0].ocupacion_actual, 40.0)

    def test_estados_del_motor_controlan_asignacion(self):
        config = ConfiguracionAutoasignacion.objects.create(pk=1, activa=False)
        PerfilAutoasignacion.objects.create(tecnico=self.tecnico, habilitado=True, cobertura_general=True, capacidad=20)
        ticket = Ticket.objects.create(titulo="Prueba", categoria=self.categoria, prioridad="alta")
        with patch.object(connection.features, "has_select_for_update", True), patch.object(connection.ops, "for_update_sql", return_value=""):
            self.assertIsNone(asignar_ticket(ticket.pk))
            config.activa = True
            config.save(update_fields=["activa"])
            self.assertEqual(asignar_ticket(ticket.pk).candidato.pk, self.tecnico.pk)
