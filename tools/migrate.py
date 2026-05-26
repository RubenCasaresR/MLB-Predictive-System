#!/usr/bin/env python
"""
CLI helper para gestionar migraciones Alembic.

Uso:
    python tools/migrate.py status        # Ver estado actual
    python tools/migrate.py upgrade       # Aplicar todas las migraciones pendientes
    python tools/migrate.py downgrade     # Revertir última migración
    python tools/migrate.py stamp         # Marcar DB como actual (sin ejecutar)
    python tools/migrate.py history       # Ver historial de migraciones
    python tools/migrate.py new "message" # Crear nueva migración vacía
"""

import logging
import subprocess
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("migrate")

ALEMBIC_CMD = [sys.executable, "-m", "alembic"]


def _run(args: list) -> int:
    cmd = ALEMBIC_CMD + args
    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd)
    return result.returncode


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 0

    action = sys.argv[1]

    if action == "status":
        return _run(["current", "--verbose"])
    elif action == "upgrade":
        return _run(["upgrade", "head"])
    elif action == "downgrade":
        return _run(["downgrade", "-1"])
    elif action == "stamp":
        return _run(["stamp", "head"])
    elif action == "history":
        return _run(["history"])
    elif action == "new":
        if len(sys.argv) < 3:
            print('Uso: python tools/migrate.py new "mensaje de migración"')
            return 1
        msg = sys.argv[2]
        return _run(["revision", "--autogenerate", "-m", msg])
    else:
        print(f"Acción desconocida: {action}")
        print(__doc__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
