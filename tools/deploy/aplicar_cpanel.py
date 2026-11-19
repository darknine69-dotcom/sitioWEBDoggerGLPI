"""Ejecución explícita desde Setup Python App; aplica el ZIP situado al lado."""
import os
from pathlib import Path
from paquete import instalar

if __name__ == "__main__":
    raiz = os.environ.get("DOGGER_DEPLOY_ROOT")
    if not raiz:
        raise SystemExit("Configure DOGGER_DEPLOY_ROOT antes de aplicar.")
    instalar(Path(__file__).with_name("dogger_update.zip"), Path(raiz), aplicar=True)
