#!/usr/bin/env python3
"""
setup_plugins.py
═════════════════════════════════════════════════════════════════════════════
Script de automatización: Mapea plugins desde src/05_plugins/ a ~/.fiftyone/plugins/

Propósito:
  Durante desarrollo, los plugins residen en src/05_plugins/ para versionarse
  en Git. Sin embargo, FiftyOne solo descubre plugins bajo ~/.fiftyone/plugins/.
  Este script automatiza el mapeo (symlink o copia) de forma cross-platform.

Uso:
  python setup_plugins.py [--mode {link|copy}] [--force]

  --mode {link|copy}    : 'link' = crear symlinks (defecto en Unix);
                          'copy' = copiar directorios completos (defecto en Windows)
  --force               : Sobreescribir plugins existentes en ~/.fiftyone/plugins/

Flujo de ejecución:
  1. Localiza src/05_plugins/ en la raíz del proyecto
  2. Itera sobre subdirectorios con fiftyone.yml
  3. Por cada plugin, crea un symlink o copia el directorio a ~/.fiftyone/plugins/
  4. Registra el mapeo en un archivo de auditoría: ~/.fiftyone/plugins/.setup.log

Plataformas soportadas:
  ✅ Linux   : symlinks nativos (ln -s)
  ✅ macOS   : symlinks nativos (ln -s)
  ✅ Windows : mklink /D (requiere permisos administrativos) o fallback a copiar

═════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE LOGGING
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

PLUGINS_SOURCE_DIR = Path(__file__).parent / "05_plugins"
"""Ubicación en el repo donde residen los plugins en desarrollo."""

PLUGINS_DEST_DIR = Path.home() / ".fiftyone" / "plugins"
"""Ubicación donde FiftyOne busca plugins automáticamente."""

SETUP_LOG_FILE = PLUGINS_DEST_DIR / ".setup.log"
"""Archivo de auditoría: registro de qué plugins fueron mapeados y cuándo."""

CURRENT_PLATFORM = sys.platform
"""Identificador de plataforma: 'linux', 'darwin' (macOS), 'win32' (Windows)."""


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES AUXILIARES
# ─────────────────────────────────────────────────────────────────────────────


def _is_plugin_dir(path: Path) -> bool:
    """Verifica si un directorio contiene un plugin válido (debe tener fiftyone.yml)."""
    return (path / "fiftyone.yml").exists() and path.is_dir()


def _can_create_symlink() -> bool:
    """
    Verifica si el sistema permite crear symlinks sin permisos administrativos.
    
    En Windows, los symlinks requieren admin (o modo developer habilitado).
    En Unix (Linux, macOS), son triviales.
    """
    if CURRENT_PLATFORM != "win32":
        return True  # Unix: symlinks siempre disponibles

    # Windows: intentar crear un symlink temporal para verificar permisos
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            src = tmpdir / "src_test"
            dst = tmpdir / "link_test"
            src.touch()
            os.symlink(src, dst)
            return True
    except (OSError, NotImplementedError):
        return False


def _create_plugin_mapping(
    plugin_dir: Path,
    dest_plugin_dir: Path,
    mode: Literal["link", "copy"],
    force: bool = False,
) -> bool:
    """
    Crea el mapeo de un plugin individual (symlink o copia).
    
    Args:
        plugin_dir: Ruta fuente en src/05_plugins/nombre_plugin/
        dest_plugin_dir: Ruta destino en ~/.fiftyone/plugins/nombre_plugin/
        mode: 'link' para symlink, 'copy' para copia de directorio
        force: Si True, sobrescribe si el destino ya existe
        
    Returns:
        True si el mapeo fue exitoso, False en caso contrario.
    """
    plugin_name = plugin_dir.name

    # Verificar si el destino ya existe
    if dest_plugin_dir.exists():
        if not force:
            logger.warning(
                f"Plugin '{plugin_name}' ya existe en {dest_plugin_dir}. "
                f"Usa --force para sobrescribir."
            )
            return False

        # Eliminar el destino existente
        if dest_plugin_dir.is_symlink():
            dest_plugin_dir.unlink()
            logger.info(f"Symlink previo eliminado: {dest_plugin_dir}")
        else:
            shutil.rmtree(dest_plugin_dir)
            logger.info(f"Directorio previo eliminado: {dest_plugin_dir}")

    try:
        if mode == "link":
            # Crear symlink
            os.symlink(plugin_dir, dest_plugin_dir)
            logger.info(f"✅ Symlink creado: {dest_plugin_dir} → {plugin_dir}")
            return True
        else:  # mode == "copy"
            # Copiar directorio completo
            shutil.copytree(plugin_dir, dest_plugin_dir)
            logger.info(f"✅ Plugin copiado: {plugin_dir} → {dest_plugin_dir}")
            return True

    except Exception as e:
        logger.error(f"❌ Error al mapear plugin '{plugin_name}': {e}")
        return False


def _log_setup_event(message: str) -> None:
    """Registra eventos en el archivo de auditoría ~/.fiftyone/plugins/.setup.log."""
    SETUP_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETUP_LOG_FILE, "a", encoding="utf-8") as f:
        timestamp = datetime.now().isoformat()
        f.write(f"[{timestamp}] {message}\n")


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────


def main():
    """Punto de entrada: mapea todos los plugins de src/05_plugins/ a ~/.fiftyone/plugins/."""
    
    parser = argparse.ArgumentParser(
        description="Setup de plugins: mapea src/05_plugins/ → ~/.fiftyone/plugins/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Ejemplos:
  python setup_plugins.py              # Modo automático (link en Unix, copy en Windows)
  python setup_plugins.py --mode link  # Forzar symlinks
  python setup_plugins.py --mode copy  # Forzar copia de directorios
  python setup_plugins.py --force      # Sobrescribir plugins existentes
        """,
    )

    parser.add_argument(
        "--mode",
        choices=["link", "copy"],
        default=None,
        help="Modo de mapeo: 'link' (symlink) o 'copy' (copia). "
        "Si no se especifica, se usa 'link' en Unix y 'copy' en Windows.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Sobrescribir plugins existentes sin confirmar.",
    )

    args = parser.parse_args()

    # ─────────────────────────────────────────────────────────────────────────
    # VALIDACIONES PREVIAS
    # ─────────────────────────────────────────────────────────────────────────

    if not PLUGINS_SOURCE_DIR.exists():
        logger.error(f"❌ Directorio de plugins no encontrado: {PLUGINS_SOURCE_DIR}")
        logger.error(f"   Asegúrate de ejecutar este script desde la raíz del repo.")
        sys.exit(1)

    # Crear ~/.fiftyone/plugins/ si no existe
    PLUGINS_DEST_DIR.mkdir(parents=True, exist_ok=True)

    # Determinar modo automáticamente si no se especificó
    if args.mode is None:
        if CURRENT_PLATFORM == "win32":
            mode = "copy"  # Windows: copiar (más seguro que symlinks)
            logger.info(f"Windows detectado. Modo automático: --mode copy")
        else:
            mode = "link"  # Unix: symlinks
            logger.info(f"Unix detectado. Modo automático: --mode link")
    else:
        mode = args.mode

    # Validar que el modo sea viable
    if mode == "link" and not _can_create_symlink():
        logger.warning(
            "⚠️  Los symlinks no están disponibles en este sistema "
            "(en Windows requiere admin o modo developer)."
        )
        logger.warning("   Fallback a --mode copy automático.")
        mode = "copy"

    logger.info(f"Modo seleccionado: {mode}")
    logger.info(f"Fuente de plugins: {PLUGINS_SOURCE_DIR}")
    logger.info(f"Destino: {PLUGINS_DEST_DIR}")

    # ─────────────────────────────────────────────────────────────────────────
    # MAPEO DE PLUGINS
    # ─────────────────────────────────────────────────────────────────────────

    plugins_found = list(PLUGINS_SOURCE_DIR.iterdir())
    if not plugins_found:
        logger.warning(f"⚠️  No se encontraron plugins en {PLUGINS_SOURCE_DIR}")
        _log_setup_event(f"Ejecución: No se encontraron plugins en {PLUGINS_SOURCE_DIR}")
        return

    valid_plugins = [p for p in plugins_found if _is_plugin_dir(p)]

    if not valid_plugins:
        logger.warning(
            f"⚠️  No se encontraron directorios con fiftyone.yml en {PLUGINS_SOURCE_DIR}"
        )
        _log_setup_event(f"Ejecución: No se encontraron plugins válidos (sin fiftyone.yml)")
        return

    logger.info(f"Plugins encontrados: {len(valid_plugins)}")
    for plugin in valid_plugins:
        logger.info(f"  - {plugin.name}")

    print()

    # Mapear cada plugin
    success_count = 0
    for plugin_dir in valid_plugins:
        dest_plugin_dir = PLUGINS_DEST_DIR / plugin_dir.name
        if _create_plugin_mapping(plugin_dir, dest_plugin_dir, mode, args.force):
            success_count += 1

    # ─────────────────────────────────────────────────────────────────────────
    # RESUMEN Y AUDITORÍA
    # ─────────────────────────────────────────────────────────────────────────

    print()
    logger.info("=" * 70)
    logger.info(f"RESUMEN: {success_count}/{len(valid_plugins)} plugins mapeados exitosamente.")

    if success_count == len(valid_plugins):
        logger.info("✅ Setup completado. Los plugins son visibles para FiftyOne.")
        logger.info("")
        logger.info("Próximos pasos:")
        logger.info("  1. Inicia la App de FiftyOne: python -c 'import fiftyone as fo; fo.launch_app()'")
        logger.info("  2. Los plugins aparecerán en el panel de Operators (atajo: `)")
        _log_setup_event(
            f"SUCCESS: {success_count} plugins mapeados en modo '{mode}' (force={args.force})"
        )
    else:
        logger.warning(f"⚠️  Algunos plugins no se mapearon correctamente.")
        _log_setup_event(
            f"PARTIAL: {success_count}/{len(valid_plugins)} plugins mapeados en modo '{mode}'"
        )
        sys.exit(1)

    logger.info("=" * 70)


if __name__ == "__main__":
    main()
