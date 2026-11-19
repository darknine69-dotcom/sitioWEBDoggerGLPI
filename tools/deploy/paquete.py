"""Paquetes incrementales: crea, valida o simula/aplica en un destino explícito.

Por defecto, sin argumentos, solo valida y simula `dogger_update.zip` junto
al script, contra DOGGER_DEPLOY_ROOT. Ningún modo ejecuta migraciones.
"""
import argparse
import ast
from contextlib import contextmanager
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

MAX_FILE = 10 * 1024 * 1024
MAX_TOTAL = 100 * 1024 * 1024
RAICES = {"apps", "config", "templates", "static", "tools"}
EXTENSIONES = {".py", ".html", ".css", ".js", ".svg", ".json"}
ARCHIVOS_RAIZ = {"requirements.txt", "passenger_wsgi.py"}
DENEGADOS = {".env", ".git", ".venv", "venv", "media", "__pycache__", "migrations", "staticfiles", "node_modules"}
PATRON_SECRETO = re.compile(rb"(?im)^\s*(?:secret_key|client_secret|password|passwd|api_key|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]")


def sha(datos):
    return hashlib.sha256(datos).hexdigest()


def ruta_segura(nombre):
    if not isinstance(nombre, str) or "\\" in nombre or "\x00" in nombre or nombre.startswith("/") or ":" in nombre:
        raise ValueError("Ruta inválida")
    p = PurePosixPath(nombre)
    if p.as_posix() != nombre or any(x in ("", ".", "..") or x.startswith(".") or x.lower() in DENEGADOS for x in p.parts):
        raise ValueError("Ruta no permitida: " + nombre)
    if nombre not in ARCHIVOS_RAIZ and (len(p.parts) < 2 or p.parts[0] not in RAICES or p.suffix.lower() not in EXTENSIONES):
        raise ValueError("Archivo fuera del alcance permitido: " + nombre)
    return p


def revisar_codigo(nombre, datos):
    if len(datos) > MAX_FILE or PATRON_SECRETO.search(datos):
        raise ValueError("Archivo demasiado grande o contiene un posible secreto: " + nombre)
    if nombre.endswith(".py"):
        ast.parse(datos, filename=nombre)


def validar(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        entradas = z.infolist()
        nombres = [e.filename for e in entradas]
        if len(nombres) != len(set(nombres)) or len(nombres) != len({n.casefold() for n in nombres}) or "manifest.json" not in nombres:
            raise ValueError("Entradas duplicadas o manifiesto ausente")
        if sum(e.file_size for e in entradas) > MAX_TOTAL:
            raise ValueError("Paquete demasiado grande")
        for e in entradas:
            if e.is_dir() or stat.S_ISLNK(e.external_attr >> 16) or e.file_size > MAX_FILE:
                raise ValueError("Entrada inválida o enlace simbólico")
        manifiesto = json.loads(z.read("manifest.json"))
        if set(manifiesto) != {"version", "archivos"} or manifiesto["version"] != 1 or not isinstance(manifiesto["archivos"], list):
            raise ValueError("Manifiesto inválido")
        registros = manifiesto["archivos"]
        esperados = set()
        contenidos = {}
        for registro in registros:
            if set(registro) != {"ruta", "sha256", "base_sha256"}:
                raise ValueError("Registro de manifiesto inválido")
            ruta = str(ruta_segura(registro["ruta"]))
            if ruta in esperados:
                raise ValueError("Ruta duplicada")
            esperado = registro["sha256"]
            base = registro["base_sha256"]
            if not isinstance(esperado, str) or not re.fullmatch(r"[0-9a-f]{64}", esperado) or (base is not None and (not isinstance(base, str) or not re.fullmatch(r"[0-9a-f]{64}", base))):
                raise ValueError("Hash inválido")
            datos = z.read("files/" + ruta)
            if sha(datos) != esperado:
                raise ValueError("Hash incorrecto: " + ruta)
            revisar_codigo(ruta, datos)
            esperados.add(ruta)
            contenidos[ruta] = datos
        if not registros or set(nombres) != {"manifest.json"} | {"files/" + r for r in esperados}:
            raise ValueError("Contenido inesperado o paquete vacío")
        return registros, contenidos


def crear(raiz, salida, nombres):
    registros, contenidos = [], {}
    for nombre in sorted(set(nombres)):
        p = ruta_segura(nombre.replace("\\", "/"))
        ruta = destino_seguro(raiz, p)
        if not ruta.is_file():
            raise ValueError("El archivo debe existir: " + str(p))
        datos = ruta.read_bytes()
        revisar_codigo(str(p), datos)
        try:
            anterior = subprocess.run(["git", "show", "HEAD:" + str(p)], cwd=raiz, capture_output=True)
            base = sha(anterior.stdout) if anterior.returncode == 0 else None
        except FileNotFoundError:
            base = None  # Sin evidencia de base solo puede instalarse como archivo nuevo.
        registros.append({"ruta": str(p), "sha256": sha(datos), "base_sha256": base})
        contenidos[str(p)] = datos
    if not registros:
        raise ValueError("Seleccione al menos un archivo")
    with zipfile.ZipFile(salida, "x", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps({"version": 1, "archivos": registros}, ensure_ascii=False, indent=2))
        for nombre, datos in contenidos.items():
            z.writestr("files/" + nombre, datos)
    validar(salida)


def destino_seguro(raiz, relativa):
    actual = raiz
    for parte in relativa.parts:
        actual = actual / parte
        if actual.is_symlink():
            raise ValueError("Enlace simbólico en destino: " + str(relativa))
    if not actual.resolve().is_relative_to(raiz):
        raise ValueError("Ruta fuera del destino")
    return actual


@contextmanager
def bloqueo(raiz):
    raiz = raiz.resolve(strict=True)
    lock = raiz / ".dogger_deploy_lock"
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise RuntimeError("Hay otro despliegue o un bloqueo que requiere revisión manual") from exc
    try:
        yield
    finally:
        lock.rmdir()


def instalar(zip_path, raiz, aplicar=False):
    if aplicar:
        with bloqueo(raiz):
            return _instalar(zip_path, raiz, aplicar=True)
    return _instalar(zip_path, raiz, aplicar=False)


def _instalar(zip_path, raiz, aplicar=False):
    raiz = raiz.resolve(strict=True)
    registros, contenidos = validar(zip_path)
    for r in registros:
        ruta = destino_seguro(raiz, PurePosixPath(r["ruta"]))
        actual = sha(ruta.read_bytes()) if ruta.is_file() else None
        if actual not in (r["base_sha256"], r["sha256"]):
            raise ValueError("Conflicto con archivo existente: " + r["ruta"])
        padre = ruta.parent
        while not padre.exists():
            padre = padre.parent
        if not os.access(padre, os.W_OK):
            raise PermissionError("Destino sin escritura: " + r["ruta"])
    registros = [r for r in registros if not (destino_seguro(raiz, PurePosixPath(r["ruta"])).is_file()
                 and sha(destino_seguro(raiz, PurePosixPath(r["ruta"])).read_bytes()) == r["sha256"])]
    if not aplicar:
        print(f"Simulación correcta: {len(registros)} archivo(s); no se modificó nada.")
        return
    if not registros:
        print("Los archivos ya están actualizados; no se modificó nada.")
        return
    respaldo_raiz = raiz / ".dogger_deploy_backups"
    if respaldo_raiz.is_symlink():
        raise ValueError("La carpeta de respaldos no puede ser enlace simbólico")
    respaldo = respaldo_raiz / uuid.uuid4().hex
    respaldo.mkdir(parents=True, exist_ok=False)
    procesados = []
    (respaldo / "informe.json").write_text(json.dumps({"archivos": registros}, indent=2), encoding="utf-8")
    try:
        for r in registros:
            relativa = PurePosixPath(r["ruta"])
            destino = destino_seguro(raiz, relativa)
            existia = destino.exists()
            if existia:
                copia = respaldo.joinpath(*relativa.parts)
                copia.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destino, copia)
                if sha(copia.read_bytes()) != sha(destino.read_bytes()):
                    raise RuntimeError("Respaldo incorrecto: " + r["ruta"])
            destino.parent.mkdir(parents=True, exist_ok=True)
            procesados.append((destino, relativa, existia))
            with tempfile.NamedTemporaryFile(dir=destino.parent, delete=False) as tmp:
                temporal = Path(tmp.name)
                try:
                    tmp.write(contenidos[r["ruta"]])
                except BaseException:
                    temporal.unlink(missing_ok=True)
                    raise
            if existia:
                os.chmod(temporal, stat.S_IMODE(destino.stat().st_mode))
            try:
                os.replace(temporal, destino)
            finally:
                temporal.unlink(missing_ok=True)
    except BaseException:
        for destino, relativa, existia in reversed(procesados):
            if existia:
                shutil.copy2(respaldo.joinpath(*relativa.parts), destino)
            else:
                destino.unlink(missing_ok=True)
        raise
    print("Aplicado. Respaldo:", respaldo)


def restaurar(raiz, identificador):
    with bloqueo(raiz):
        return _restaurar(raiz, identificador)


def _restaurar(raiz, identificador):
    raiz = raiz.resolve(strict=True)
    if not re.fullmatch(r"[0-9a-f]{32}", identificador):
        raise ValueError("Identificador de respaldo inválido")
    carpeta = raiz / ".dogger_deploy_backups" / identificador
    if carpeta.is_symlink() or carpeta.parent.is_symlink() or not carpeta.is_dir():
        raise ValueError("Respaldo inválido")
    registros = json.loads((carpeta / "informe.json").read_text(encoding="utf-8"))["archivos"]
    pendientes = []
    for registro in registros:
        relativa = ruta_segura(registro["ruta"])
        destino = destino_seguro(raiz, relativa)
        copia = carpeta.joinpath(*relativa.parts)
        actual = sha(destino.read_bytes()) if destino.is_file() else None
        if actual == registro["base_sha256"]:
            continue
        if actual != registro["sha256"]:
            raise ValueError("El archivo cambió después del despliegue: " + str(relativa))
        if registro["base_sha256"] is not None:
            if copia.is_symlink() or not copia.is_file() or sha(copia.read_bytes()) != registro["base_sha256"]:
                raise ValueError("Respaldo ausente o corrupto: " + str(relativa))
        pendientes.append(registro)
    for registro in pendientes:
        relativa = ruta_segura(registro["ruta"])
        destino = destino_seguro(raiz, relativa)
        if registro["base_sha256"] is not None:
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(carpeta.joinpath(*relativa.parts), destino)
        elif destino.exists():
            destino.unlink()
    print("Respaldo restaurado:", identificador)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--crear", type=Path)
    parser.add_argument("--validar", type=Path)
    parser.add_argument("--instalar", type=Path)
    parser.add_argument("--restaurar", metavar="ID")
    parser.add_argument("--raiz", type=Path, default=Path(os.environ["DOGGER_DEPLOY_ROOT"]) if os.environ.get("DOGGER_DEPLOY_ROOT") else None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("archivos", nargs="*")
    args = parser.parse_args()
    if args.apply and args.dry_run:
        parser.error("No combine --apply con --dry-run")
    if args.restaurar:
        if args.raiz is None:
            parser.error("Configure DOGGER_DEPLOY_ROOT o indique --raiz")
        restaurar(args.raiz, args.restaurar)
    elif args.crear:
        crear(Path.cwd().resolve(), args.crear, args.archivos)
    elif args.validar:
        registros, _ = validar(args.validar)
        print(f"Paquete válido: {len(registros)} archivo(s).")
    else:
        if args.raiz is None:
            parser.error("Configure DOGGER_DEPLOY_ROOT o indique --raiz")
        instalar(args.instalar or Path(__file__).with_name("dogger_update.zip"), args.raiz, args.apply)


if __name__ == "__main__":
    main()
