"""Restauración explícita desde Setup Python App con un ID de respaldo."""
import os
from pathlib import Path
from paquete import restaurar

if __name__ == "__main__":
    raiz = os.environ.get("DOGGER_DEPLOY_ROOT")
    respaldo = os.environ.get("DOGGER_DEPLOY_BACKUP_ID")
    if not raiz or not respaldo:
        raise SystemExit("Configure DOGGER_DEPLOY_ROOT y DOGGER_DEPLOY_BACKUP_ID.")
    restaurar(Path(raiz), respaldo)
