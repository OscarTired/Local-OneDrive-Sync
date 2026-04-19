"""
sync.py - Sincronización unidireccional Local → OneDrive usando robocopy.

Uso:
    python sync.py              Ejecuta la sincronización una vez.
    python sync.py --dry-run    Muestra qué se copiaría sin ejecutar cambios.
    python sync.py --install-task   Registra tarea programada en Windows.
    python sync.py --uninstall-task Elimina la tarea programada.
"""

import json
import logging
import os
import subprocess
import sys
from argparse import ArgumentParser
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
TASK_NAME = "SyncLocalToOneDrive"

# Códigos de salida de robocopy (bitmask)
ROBOCOPY_SUCCESS_FLAGS = {
    0: "Sin cambios.",
    1: "Archivos copiados exitosamente.",
    2: "Archivos extra detectados en destino (eliminados por /MIR).",
    3: "Archivos copiados y extras eliminados.",
    4: "Archivos o directorios con discrepancias encontrados.",
    5: "Archivos copiados y discrepancias encontradas.",
    6: "Extras eliminados y discrepancias encontradas.",
    7: "Archivos copiados, extras eliminados y discrepancias encontradas.",
}


def load_config() -> dict:
    """Carga y valida el archivo de configuración."""
    if not CONFIG_PATH.exists():
        print(f"ERROR: No se encontró {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    required = ["source", "destination"]
    for key in required:
        if key not in config or not config[key]:
            print(f"ERROR: Falta la clave '{key}' en config.json")
            sys.exit(1)

    # Valores por defecto
    config.setdefault("log_file", str(SCRIPT_DIR / "sync.log"))
    config.setdefault("log_max_mb", 5)
    config.setdefault("exclude_dirs", [])
    config.setdefault("exclude_files", [])
    config.setdefault("robocopy_threads", 8)
    config.setdefault("retry_count", 2)
    config.setdefault("retry_wait_seconds", 3)
    config.setdefault("schedule_interval_minutes", 5)

    return config


def setup_logging(config: dict) -> logging.Logger:
    """Configura logging con rotación de archivo."""
    logger = logging.getLogger("sync")
    logger.setLevel(logging.INFO)

    # Handler de archivo con rotación
    max_bytes = config["log_max_mb"] * 1024 * 1024
    fh = RotatingFileHandler(
        config["log_file"],
        maxBytes=max_bytes,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.INFO)

    # Handler de consola
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger


def build_robocopy_cmd(config: dict, dry_run: bool = False) -> list[str]:
    """Construye el comando robocopy a partir de la configuración."""
    src = config["source"]
    dst = config["destination"]
    threads = config["robocopy_threads"]
    retries = config["retry_count"]
    wait = config["retry_wait_seconds"]

    cmd = [
        "robocopy",
        src,
        dst,
        "/MIR",              # Espejo completo (copia, actualiza, elimina)
        f"/MT:{threads}",    # Multihilo
        f"/R:{retries}",     # Reintentos por archivo
        f"/W:{wait}",        # Espera entre reintentos (seg)
        "/NP",               # Sin porcentaje de progreso (log limpio)
        "/NDL",              # Sin listado de directorios
        "/NFL",              # Sin listado de archivos (resumen solamente)
        "/NJH",              # Sin encabezado de trabajo
        "/NJS",              # Sin resumen de trabajo (lo hacemos en Python)
        "/BYTES",            # Tamaños en bytes para parseo
    ]

    if dry_run:
        cmd.append("/L")    # Solo listar, no ejecutar

    # Exclusiones de directorios
    if config["exclude_dirs"]:
        cmd.append("/XD")
        cmd.extend(config["exclude_dirs"])

    # Exclusiones de archivos
    if config["exclude_files"]:
        cmd.append("/XF")
        cmd.extend(config["exclude_files"])

    return cmd


def run_sync(config: dict, logger: logging.Logger, dry_run: bool = False) -> int:
    """Ejecuta la sincronización con robocopy."""
    src = Path(config["source"])
    dst = Path(config["destination"])

    # Validar que el origen existe
    if not src.exists():
        logger.error(f"La carpeta origen no existe: {src}")
        return -1

    # Crear destino si no existe
    if not dst.exists():
        logger.info(f"Creando carpeta destino: {dst}")
        dst.mkdir(parents=True, exist_ok=True)

    mode = "SIMULACIÓN" if dry_run else "SINCRONIZACIÓN"
    logger.info(f"=== {mode} INICIADA ===")
    logger.info(f"Origen:  {src}")
    logger.info(f"Destino: {dst}")

    cmd = build_robocopy_cmd(config, dry_run)
    logger.info(f"Comando: {' '.join(cmd)}")

    start = datetime.now()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        logger.error("robocopy no encontrado. Asegúrate de estar en Windows.")
        return -1

    elapsed = (datetime.now() - start).total_seconds()
    exit_code = result.returncode

    # Robocopy: códigos 0-7 son éxito, 8+ son errores
    if exit_code < 8:
        desc = ROBOCOPY_SUCCESS_FLAGS.get(exit_code, "Completado.")
        logger.info(f"Resultado (código {exit_code}): {desc}")
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                if line.strip():
                    logger.info(f"  {line.strip()}")
    else:
        logger.error(f"robocopy falló con código {exit_code}")
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                if line.strip():
                    logger.error(f"  {line.strip()}")
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                if line.strip():
                    logger.error(f"  STDERR: {line.strip()}")

    logger.info(f"Tiempo transcurrido: {elapsed:.1f} segundos")
    logger.info(f"=== {mode} FINALIZADA ===\n")

    return exit_code


def get_python_executable() -> str:
    """Devuelve la ruta al ejecutable Python del entorno virtual o del sistema."""
    venv_python = SCRIPT_DIR / "venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def install_task(config: dict):
    """Registra la tarea programada en Windows Task Scheduler."""
    interval = config["schedule_interval_minutes"]
    python_exe = get_python_executable()
    script_path = str(SCRIPT_DIR / "sync.py")

    # schtasks requiere un formato de repetición
    cmd = [
        "schtasks", "/create",
        "/tn", TASK_NAME,
        "/tr", f'"{python_exe}" "{script_path}"',
        "/sc", "MINUTE",
        "/mo", str(interval),
        "/f",  # Forzar creación (sobrescribe si existe)
    ]

    print(f"Registrando tarea '{TASK_NAME}' cada {interval} minutos...")
    print(f"Python: {python_exe}")
    print(f"Script: {script_path}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Tarea '{TASK_NAME}' creada exitosamente.")
            print(f"Se ejecutará cada {interval} minutos.")
        else:
            print(f"Error al crear la tarea (código {result.returncode}):")
            print(result.stdout)
            print(result.stderr)
            print("\nNOTA: Puede requerir ejecutar como Administrador.")
    except Exception as e:
        print(f"Error: {e}")


def uninstall_task():
    """Elimina la tarea programada de Windows Task Scheduler."""
    cmd = ["schtasks", "/delete", "/tn", TASK_NAME, "/f"]

    print(f"Eliminando tarea '{TASK_NAME}'...")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Tarea '{TASK_NAME}' eliminada exitosamente.")
        else:
            print(f"Error al eliminar la tarea (código {result.returncode}):")
            print(result.stdout)
            print(result.stderr)
    except Exception as e:
        print(f"Error: {e}")


def main():
    parser = ArgumentParser(description="Sincronización Local → OneDrive")
    parser.add_argument("--dry-run", action="store_true", help="Simula la sincronización sin ejecutar cambios")
    parser.add_argument("--install-task", action="store_true", help="Registra tarea programada en Windows")
    parser.add_argument("--uninstall-task", action="store_true", help="Elimina la tarea programada")
    args = parser.parse_args()

    config = load_config()

    if args.install_task:
        install_task(config)
        return

    if args.uninstall_task:
        uninstall_task()
        return

    logger = setup_logging(config)

    exit_code = run_sync(config, logger, dry_run=args.dry_run)

    # Salir con código apropiado (0 si robocopy retornó 0-7)
    sys.exit(0 if 0 <= exit_code < 8 else 1)


if __name__ == "__main__":
    main()
