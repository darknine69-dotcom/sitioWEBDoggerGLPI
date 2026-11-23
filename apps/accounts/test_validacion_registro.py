from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.forms import UserRegisterForm


class ValidacionRegistroTests(TestCase):
    def datos(self, **cambios):
        datos = {"nombre": "Ana", "email": "ana@example.com", "password1": "Bosque#Luz47Segura", "password2": "Bosque#Luz47Segura"}
        datos.update(cambios)
        return datos

    def test_rechaza_correo_mal_formado(self):
        form = UserRegisterForm(self.datos(email="ana@correo"))
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_rechaza_correo_duplicado_sin_importar_mayusculas(self):
        get_user_model().objects.create_user("Ana@example.com", "Ana", "clave")
        form = UserRegisterForm(self.datos(email="ana@example.com"))
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_rechaza_contrasena_corta_comun_o_numerica(self):
        for clave in ("Ab1!", "password123", "1234567890"):
            with self.subTest(clave=clave):
                form = UserRegisterForm(self.datos(password1=clave, password2=clave))
                self.assertFalse(form.is_valid())
                self.assertIn("password1", form.errors)

    def test_rechaza_confirmacion_distinta(self):
        form = UserRegisterForm(self.datos(password2="Otra#Clave654"))
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_acepta_datos_validos(self):
        self.assertTrue(UserRegisterForm(self.datos()).is_valid())
