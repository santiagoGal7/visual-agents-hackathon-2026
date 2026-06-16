#!/usr/bin/env python3
"""
verify_env.py
═════════════════════════════════════════════════════════════════════════════
Script de validación defensiva del entorno local de desarrollo.
Repositorio: https://github.com/santiagoGal7/visual-agents-hackathon-2026.git

Ejecutar desde la raíz del proyecto:
    python src/01_setup/verify_env.py

Verifica:
  1. Versión de Python == 3.11.x
  2. Importación y versión de FiftyOne
  3. Conectividad con MongoDB local (puerto 27017) via DatasetView de prueba
  4. Presencia de OPENAI_API_KEY y ANTHROPIC_API_KEY en variables de entorno

Exit codes:
  0 → Todos los checks críticos pasaron (warnings no cuentan como fallo)
  1 → Al menos un check crítico falló
═════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import os
import sys
import textwrap
import time
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES DE PRESENTACIÓN EN CONSOLA
# ─────────────────────────────────────────────────────────────────────────────

WIDTH = 68  # Ancho del banner


def _banner() -> None:
    """Imprime el banner de bienvenida del script."""
    print()
    print("╔" + "═" * (WIDTH - 2) + "╗")
    print("║" + " Visual Agents Hackathon 2026 — Environment Verifier ".center(WIDTH - 2) + "║")
    print("║" + " github.com/santiagoGal7/visual-agents-hackathon-2026 ".center(WIDTH - 2) + "║")
    print("╚" + "═" * (WIDTH - 2) + "╝")
    print()


def _section(title: str) -> None:
    """Imprime un separador de sección con título."""
    print()
    print("  ┌─ " + title)
    print("  │")


def _close_section() -> None:
    """Cierra visualmente una sección."""
    print("  │")


def _ok(message: str) -> None:
    """Imprime una línea de éxito."""
    print(f"  │  ✅  {message}")


def _warn(message: str) -> None:
    """Imprime una línea de advertencia (no crítica)."""
    print(f"  │  ⚠️   {message}")


def _fail(message: str) -> None:
    """Imprime una línea de error crítico."""
    print(f"  │  ❌  {message}")


def _info(message: str) -> None:
    """Imprime una línea informativa neutral."""
    print(f"  │     {message}")


def _summary(passed: int, warned: int, failed: int) -> None:
    """Imprime el resumen final de todos los checks."""
    print()
    print("  ┌" + "─" * (WIDTH - 4) + "┐")
    print("  │" + " RESUMEN DE VALIDACIÓN ".center(WIDTH - 4) + "│")
    print("  ├" + "─" * (WIDTH - 4) + "┤")
    print(f"  │  ✅  Checks pasados  : {passed:<3}                              │")
    print(f"  │  ⚠️   Advertencias    : {warned:<3}                              │")
    print(f"  │  ❌  Checks fallidos : {failed:<3}                              │")
    print("  └" + "─" * (WIDTH - 4) + "┘")
    print()

    if failed == 0:
        print("  🚀  Entorno listo. ¡A hackear!")
    else:
        print("  🔧  Corrige los errores marcados con ❌ antes de continuar.")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 1: VERSIÓN DE PYTHON
# ─────────────────────────────────────────────────────────────────────────────

def check_python_version() -> bool:
    """
    Verifica que el intérprete activo sea estrictamente Python 3.11.x.

    Returns:
        True si la versión es 3.11.x, False en cualquier otro caso.
    """
    _section("CHECK 1 · Versión de Python")

    major = sys.version_info.major
    minor = sys.version_info.minor
    micro = sys.version_info.micro
    full_version = f"{major}.{minor}.{micro}"

    _info(f"Intérprete activo : {sys.executable}")
    _info(f"Versión detectada : Python {full_version}")

    if major == 3 and minor == 11:
        _ok(f"Python {full_version} ✓ — versión requerida 3.11.x satisfecha.")
        _close_section()
        return True
    else:
        _fail(
            f"Python {full_version} no es compatible. "
            f"Se requiere estrictamente Python 3.11.x."
        )
        _info("  → Usa pyenv: pyenv install 3.11.9 && pyenv local 3.11.9")
        _info("  → O crea un venv: python3.11 -m venv .venv && source .venv/bin/activate")
        _close_section()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 2: IMPORTACIÓN DE FIFTYONE
# ─────────────────────────────────────────────────────────────────────────────

def check_fiftyone() -> bool:
    """
    Verifica que fiftyone esté instalado e importable, e imprime su versión.

    Returns:
        True si el import tiene éxito, False si falla.
    """
    _section("CHECK 2 · Instalación de FiftyOne")

    try:
        import importlib.metadata as importlib_metadata

        _info("Ejecutando: import fiftyone ...")
        import fiftyone as fo  # noqa: F401

        # Intentar obtener la versión desde el package metadata primero
        # (más rápido que fo.__version__ en algunos entornos)
        try:
            version = importlib_metadata.version("fiftyone")
        except importlib_metadata.PackageNotFoundError:
            version = getattr(fo, "__version__", "desconocida")

        _ok(f"fiftyone {version} importado correctamente.")
        _info(f"Ubicación del módulo : {fo.__file__}")
        _close_section()
        return True

    except ImportError as exc:
        _fail(f"No se pudo importar fiftyone: {exc}")
        _info("  → Instala con: pip install fiftyone")
        _info("  → O desde el repo: pip install -r requirements.txt")
        _close_section()
        return False

    except Exception as exc:
        _fail(f"Error inesperado al importar fiftyone: {type(exc).__name__}: {exc}")
        _close_section()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 3: CONECTIVIDAD CON MONGODB + DATASET VIEW DE PRUEBA
# ─────────────────────────────────────────────────────────────────────────────

def check_mongodb_and_fiftyone_zoo() -> bool:
    """
    Verifica la conectividad con MongoDB local en el puerto 27017 creando
    un dataset de prueba mínimo con las 5 imágenes locales de data/mock_samples/.

    Returns:
        True si la conexión y la DatasetView se crean exitosamente.
        False si MongoDB no está disponible o FiftyOne no está instalado.
    """
    _section("CHECK 3 · MongoDB (localhost:27017) + Dataset de Prueba")

    try:
        import fiftyone as fo

    except ImportError:
        _fail("fiftyone no está disponible. Resuelve el CHECK 2 primero.")
        _close_section()
        return False

    # --- Paso 3a: Verificar conectividad con MongoDB ---
    _info("Verificando conectividad con MongoDB en localhost:27017 ...")

    try:
        # fo.list_datasets() realiza una consulta liviana a MongoDB.
        # Si el daemon mongod no está corriendo, lanza una excepción de
        # conexión en < 1 segundo (timeout por defecto del driver pymongo).
        t0 = time.perf_counter()
        existing_datasets = fo.list_datasets()
        elapsed_ms = (time.perf_counter() - t0) * 1000

        _ok(f"MongoDB respondió en {elapsed_ms:.1f}ms.")
        _info(f"Datasets existentes en MongoDB : {existing_datasets or ['(ninguno)']}")

    except Exception as exc:
        _fail(f"No se pudo conectar con MongoDB: {type(exc).__name__}: {exc}")
        _info("  → Asegúrate de que mongod esté corriendo:")
        _info("       macOS  : brew services start mongodb-community")
        _info("       Linux  : sudo systemctl start mongod")
        _info("       Docker : docker run -d -p 27017:27017 mongo:7.0")
        _close_section()
        return False

    # --- Paso 3b: Crear dataset de prueba cargando imágenes locales ---
    _info("")
    _info("Creando dataset de prueba cargando 5 imágenes locales de data/mock_samples/...")

    dataset_created = False
    dataset_name = "_verify_env_test"
    try:
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        mock_samples_dir = os.path.join(root_dir, "data", "mock_samples")

        if not os.path.exists(mock_samples_dir):
            raise FileNotFoundError(f"La carpeta '{mock_samples_dir}' no existe.")

        image_extensions = (".jpg", ".jpeg", ".png")
        image_paths = [
            os.path.join(mock_samples_dir, f)
            for f in sorted(os.listdir(mock_samples_dir))
            if f.lower().endswith(image_extensions)
        ]

        if len(image_paths) < 5:
            raise FileNotFoundError(
                f"Se esperaban al menos 5 imágenes en '{mock_samples_dir}', "
                f"pero se encontraron {len(image_paths)}."
            )

        # Usar exactamente las primeras 5 imágenes
        image_paths = image_paths[:5]

        # Crear dataset de prueba
        t0 = time.perf_counter()
        
        # Eliminar dataset previo si existe
        if dataset_name in existing_datasets:
            fo.delete_dataset(dataset_name)
        
        dataset: fo.Dataset = fo.Dataset(name=dataset_name)
        dataset.persistent = True
        
        samples = []
        for path in image_paths:
            sample = fo.Sample(filepath=path)
            samples.append(sample)
            
        dataset.add_samples(samples)
        
        elapsed_s = time.perf_counter() - t0
        _ok(f"Dataset de prueba creado en {elapsed_s:.2f}s.")
        _info(f"Total de samples : {len(dataset)}")
        dataset_created = True

    except Exception as exc:
        _fail(f"No se pudo crear el dataset con imágenes locales: {type(exc).__name__}: {exc}")
        _info("  → Asegúrate de que las 5 imágenes de prueba existan en data/mock_samples/")
        _close_section()
        return False

    if not dataset_created:
        _close_section()
        return False

    # --- Paso 3c: Crear y validar una DatasetView de 5 samples ---
    _info("")
    _info("Construyendo DatasetView de prueba (limit=5) ...")

    try:
        view: fo.DatasetView = dataset.limit(5)
        view_count = len(view)

        if view_count == 0:
            _fail(
                "La DatasetView se creó pero retornó 0 samples. "
                "El dataset puede estar vacío o corrupto."
            )
            _close_section()
            return False

        _ok(f"DatasetView creada correctamente con {view_count} sample(s).")

        # Imprimir los filepaths de los samples como prueba de contenido real
        for i, sample in enumerate(view):
            _info(f"  Sample {i + 1}: {os.path.basename(sample.filepath)}")

    except Exception as exc:
        _fail(
            f"Error al construir la DatasetView: "
            f"{type(exc).__name__}: {exc}"
        )
        _close_section()
        return False

    # Limpiar: eliminar dataset de prueba
    try:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)
    except:
        pass  # Ignorar fallos de limpieza

    _close_section()
    return True


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 4: VARIABLES DE ENTORNO DE API KEYS
# ─────────────────────────────────────────────────────────────────────────────

def check_api_keys() -> tuple[bool, int]:
    """
    Verifica la presencia de OPENAI_API_KEY y ANTHROPIC_API_KEY en el entorno.

    Este check es NO crítico: la ausencia de una key emite un warning pero
    no falla el script (exit code 0 si los demás checks pasan). Ambas keys
    son necesarias para el pipeline VLM del Módulo 04, pero el entorno
    base puede estar operativo sin ellas.

    Returns:
        Tupla (all_present: bool, warnings_count: int):
          - all_present: True si ambas keys están definidas y no vacías.
          - warnings_count: número de keys faltantes (0, 1 o 2).
    """
    _section("CHECK 4 · Variables de Entorno — API Keys")

    keys_to_check = {
        "OPENAI_API_KEY": {
            "provider": "OpenAI (gpt-4o)",
            "module": "Módulo 04 — VLM Pipeline",
            "hint": "Obtén tu key en https://platform.openai.com/api-keys",
        },
        "ANTHROPIC_API_KEY": {
            "provider": "Anthropic (claude-3-5-sonnet)",
            "module": "Módulos 04 y 05 — VLM Pipeline + MCP Server",
            "hint": "Obtén tu key en https://console.anthropic.com/",
        },
    }

    warnings_count = 0
    all_present = True

    for env_var, meta in keys_to_check.items():
        value: Optional[str] = os.environ.get(env_var)

        if value and value.strip():
            # Enmascarar el valor para no exponer la key en logs
            masked = value[:4] + "..." + value[-4:] if len(value) > 8 else "***"
            _ok(f"{env_var} detectada ({masked}) → {meta['provider']}")
        else:
            _warn(f"{env_var} NO está definida.")
            _info(f"       Proveedor afectado : {meta['provider']}")
            _info(f"       Módulo afectado    : {meta['module']}")
            _info(f"       Cómo obtenerla     : {meta['hint']}")
            _info(f"       Cómo definirla     : export {env_var}='sk-...'")
            _info(f"       O agrega al .env   : {env_var}=sk-...")
            warnings_count += 1
            all_present = False

    if all_present:
        _info("")
        _ok("Ambas API keys están presentes. Pipeline VLM completamente operativo.")

    _close_section()
    return all_present, warnings_count


# ─────────────────────────────────────────────────────────────────────────────
# ORQUESTADOR PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    """
    Orquesta la ejecución secuencial de todos los checks de validación
    del entorno y retorna el exit code apropiado.

    Returns:
        0 si todos los checks críticos pasan (con o sin warnings).
        1 si al menos un check crítico falla.
    """
    _banner()

    passed = 0
    warned = 0
    failed = 0

    # --- CHECK 1: Python 3.11.x ---
    if check_python_version():
        passed += 1
    else:
        failed += 1

    # --- CHECK 2: FiftyOne importable ---
    if check_fiftyone():
        passed += 1
    else:
        failed += 1

    # --- CHECK 3: MongoDB + Zoo DatasetView ---
    if check_mongodb_and_fiftyone_zoo():
        passed += 1
    else:
        failed += 1

    # --- CHECK 4: API Keys (no crítico — warnings) ---
    keys_ok, keys_warned = check_api_keys()
    warned += keys_warned
    if keys_ok:
        passed += 1
    else:
        # El check de keys no incrementa `failed`; solo `warned`.
        # El bloque passed no se incrementa si faltan keys, pero
        # tampoco penaliza el exit code.
        pass

    # --- Resumen final ---
    _summary(passed=passed, warned=warned, failed=failed)

    return 0 if failed == 0 else 1


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
    sys.exit(main())
