import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools.deploy import paquete


class PaqueteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dogger-paquete-test-")
        self.addCleanup(self.temp.cleanup)
        self.raiz = Path(self.temp.name)
        (self.raiz / "static").mkdir()
        self.destino = self.raiz / "static" / "demo.css"
        self.destino.write_bytes(b"anterior")
        self.zip = self.raiz / "actualizacion.zip"
        self.registro = {"ruta": "static/demo.css", "sha256": paquete.sha(b"nuevo"), "base_sha256": paquete.sha(b"anterior")}
        self.escribir_zip()

    def escribir_zip(self, adicional=None, contenido=b"nuevo"):
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr("manifest.json", json.dumps({"version": 1, "archivos": [self.registro]}))
            z.writestr("files/" + self.registro["ruta"], contenido)
            if adicional:
                z.writestr(adicional, "x")

    def test_simulacion_no_cambia_archivos(self):
        paquete.instalar(self.zip, self.raiz)
        self.assertEqual(self.destino.read_bytes(), b"anterior")
        self.assertFalse((self.raiz / ".dogger_deploy_backups").exists())

    def test_aplicar_y_restaurar(self):
        paquete.instalar(self.zip, self.raiz, aplicar=True)
        self.assertEqual(self.destino.read_bytes(), b"nuevo")
        copia = next((self.raiz / ".dogger_deploy_backups").iterdir())
        paquete.restaurar(self.raiz, copia.name)
        self.assertEqual(self.destino.read_bytes(), b"anterior")

    def test_rechaza_conflicto_y_archivo_extra(self):
        self.destino.write_bytes(b"cambio-ajeno")
        with self.assertRaises(ValueError):
            paquete.instalar(self.zip, self.raiz, aplicar=True)
        self.assertEqual(self.destino.read_bytes(), b"cambio-ajeno")
        self.escribir_zip(adicional="files/../escape")
        with self.assertRaises(ValueError):
            paquete.validar(self.zip)

    def test_rechaza_hash_sin_efectos(self):
        self.escribir_zip(contenido=b"manipulado")
        with self.assertRaises(ValueError):
            paquete.instalar(self.zip, self.raiz, aplicar=True)
        self.assertEqual(self.destino.read_bytes(), b"anterior")

    def test_bloqueo_impide_dos_instaladores(self):
        with paquete.bloqueo(self.raiz):
            with self.assertRaises(RuntimeError):
                paquete.instalar(self.zip, self.raiz, aplicar=True)
        self.assertEqual(self.destino.read_bytes(), b"anterior")

    def test_rechaza_rutas_sensibles(self):
        for nombre in ("../x.py", "/tmp/x.py", "apps/a/migrations/001.py", "media/a.png", "config/.env", "C:/x.py", "apps\\x.py"):
            with self.subTest(nombre=nombre), self.assertRaises(ValueError):
                paquete.ruta_segura(nombre)

    @patch("tools.deploy.paquete.os.replace", side_effect=OSError("simulado"))
    def test_restaura_si_falla_reemplazo(self, _replace):
        with self.assertRaises(OSError):
            paquete.instalar(self.zip, self.raiz, aplicar=True)
        self.assertEqual(self.destino.read_bytes(), b"anterior")


if __name__ == "__main__":
    unittest.main()
