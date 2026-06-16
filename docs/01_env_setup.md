# 🛠️ docs/01_env_setup.md — Configuración del Entorno de Desarrollo

## Hackathon Data Agents & Visual Agents | Voxel51

---

## Introducción

Este documento establece el **protocolo único y obligatorio** de configuración de entorno para todo el equipo. El objetivo no es solo "que funcione", sino que funcione **idéntico** en las cuatro máquinas del equipo. En una hackathon, una hora perdida depurando un entorno mal configurado es una hora que el equipo rival usa para avanzar. Cada decisión de versión aquí documentada está justificada técnicamente — no es arbitraria.

Regresar a: [`README.md`](../README.md)

---

## 1. Prerrequisitos de Versiones e Incompatibilidades Críticas

### 1.1 Python 3.11 — Mandatorio, No Negociable

**Por qué Python 3.11 y no una versión más reciente:**

FiftyOne depende de un árbol de dependencias binarias compiladas (NumPy, OpenCV, PyMongo con extensiones C, motores de serialización) que requieren *wheels* precompilados para cada versión de Python. El ecosistema de wheels para versiones **experimentales o de adopción muy reciente (como Python 3.13+ o 3.14)** suele tener cobertura incompleta en el momento de publicación de release de FiftyOne, lo cual provoca:

- Fallos de instalación por ausencia de wheels compatibles, forzando compilación desde código fuente (lenta y propensa a fallos de toolchain).
- Incompatibilidades silenciosas en librerías de visión por computadora (OpenCV, Pillow-SIMD) que dependen de ABI específicos de CPython.
- Comportamientos no determinísticos en el Brain de FiftyOne al usar versiones de `scikit-learn` o `numpy` no certificadas contra esa versión de Python.

> ⚠️ **Advertencia explícita:** **NO instalar el proyecto sobre Python 3.14 ni ninguna versión experimental/pre-release.** Aunque el `pip install` pudiera "completarse" superficialmente, es altamente probable que falle en tiempo de ejecución al invocar el motor de base de datos o al computar embeddings. Python 3.11 es la versión **validada y estable** para todo el stack de este proyecto.

| Componente  | Versión Requerida | Razón                                                                                                                                           |
| ----------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **Python**  | `3.11.x`          | Máxima compatibilidad de wheels binarios con FiftyOne y su stack de visión/ML.                                                                  |
| **MongoDB** | `7.0.x`           | Motor de almacenamiento nativo de FiftyOne; la serie 7.0 es la certificada por Voxel51 para el release actual del SDK.                          |
| **Node.js** | `20 LTS`          | Requerido por el ecosistema de plugins de FiftyOne (App basada en React) y para cualquier frontend custom (Vite/React) que el equipo construya. |

### 1.2 MongoDB 7.0.x — Backend Nativo

FiftyOne **no es solo una librería de Python**: utiliza MongoDB como su capa de persistencia nativa para metadatos de datasets, samples, labels y resultados del Brain. No es opcional ni reemplazable por SQLite ni por una base "embebida" distinta. Usar una versión de MongoDB fuera de la serie `7.0.x` (por ejemplo, 8.x muy reciente o 4.x/5.x obsoletas) puede introducir incompatibilidades en el driver `pymongo` que FiftyOne fija internamente.

### 1.3 Node.js 20 LTS — Ecosistema de Plugins y Frontend

La App de FiftyOne (la interfaz visual en el puerto `5151`) está construida sobre React, y el sistema de **Plugins/Operators** (donde el Líder de Agentes construirá las Skills) requiere un entorno Node compatible para el build del frontend de plugins. Node 20 LTS garantiza soporte a largo plazo y compatibilidad con las herramientas de build (`vite`, `yarn`) que el ecosistema de FiftyOne utiliza internamente.

---

## 2. Guía de Instalación del Entorno Virtual (Python 3.11)

El aislamiento de dependencias mediante un entorno virtual es **obligatorio**. Nunca instalar dependencias del proyecto en el Python global del sistema: esto garantiza reproducibilidad entre las cuatro máquinas del equipo y evita colisiones con otras herramientas instaladas localmente.

### 2.1 Unix / Linux / macOS

```bash
# 1. Verificar que Python 3.11 está disponible en el sistema
python3.11 --version
# Salida esperada: Python 3.11.x

# 2. Crear el entorno virtual dentro del repositorio
python3.11 -m venv .venv

# 3. Activar el entorno virtual
source .venv/bin/activate

# 4. Actualizar herramientas base de empaquetado ANTES de instalar nada más
#    (pip/setuptools/wheel desactualizados son la causa #1 de fallos de build)
pip install --upgrade pip setuptools wheel

# 5. Instalación base de FiftyOne
pip install fiftyone
```

### 2.2 Windows (PowerShell)

```powershell
# 1. Verificar la versión de Python 3.11 instalada (via py launcher)
py -3.11 --version

# 2. Crear el entorno virtual
py -3.11 -m venv .venv

# 3. Activar el entorno virtual en PowerShell
.venv\Scripts\Activate.ps1

# Nota: si PowerShell bloquea la ejecución de scripts, ejecutar una sola vez:
# Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# 4. Actualizar pip, setuptools y wheel
python -m pip install --upgrade pip setuptools wheel

# 5. Instalación base de FiftyOne
pip install fiftyone
```

### 2.3 Windows (CMD)

```cmd
:: 1. Crear el entorno virtual
py -3.11 -m venv .venv

:: 2. Activar el entorno virtual en CMD
.venv\Scripts\activate.bat

:: 3. Actualizar herramientas de empaquetado
python -m pip install --upgrade pip setuptools wheel

:: 4. Instalación base de FiftyOne
pip install fiftyone
```

> ✅ **Verificación rápida post-instalación:** Ejecuta `python -c "import fiftyone as fo; print(fo.__version__)"`. Si imprime un número de versión sin trazas de error, la instalación base es correcta. El diagnóstico completo se cubre en la **Sección 4**.

---

## 3. Configuración y Orquestación de MongoDB 7.0 Local

### 3.1 Verificación de MongoDB en el Puerto 27017

Antes de lanzar cualquier dataset en FiftyOne, confirma que el daemon de MongoDB está activo y escuchando en el puerto estándar.

**En Linux/macOS:**

```bash
# Verifica si hay un proceso escuchando en el puerto 27017
lsof -i :27017

# Alternativa usando el cliente de Mongo directamente
mongosh --port 27017 --eval "db.runCommand({ ping: 1 })"
```

**En Windows (PowerShell):**

```powershell
# Verifica el puerto 27017
Get-NetTCPConnection -LocalPort 27017 -ErrorAction SilentlyContinue

# Alternativa con el cliente Mongo
mongosh --port 27017 --eval "db.runCommand({ ping: 1 })"
```

Si el comando `ping` devuelve `{ ok: 1 }`, MongoDB está operativo y FiftyOne podrá conectarse sin configuración adicional.

> 💡 **Nota importante:** FiftyOne incluye su **propio binario embebido de MongoDB** (vía el paquete `fiftyone-db`) que gestiona automáticamente si no detecta una instancia local corriendo. Esto significa que, para la mayoría de los miembros del equipo, **no es necesario instalar MongoDB manualmente** — FiftyOne lo orquesta por debajo. La verificación manual es relevante solo si el equipo decide usar una instancia de MongoDB externa o compartida (por ejemplo, para sincronizar datasets entre máquinas).

### 3.2 Variables de Entorno Críticas

FiftyOne expone variables de entorno para controlar explícitamente dónde y cómo se almacena/conecta la base de datos. Esto es crítico cuando el equipo necesita **control de infraestructura** en lugar de depender del comportamiento por defecto.

| Variable                | Propósito                                                                                                                                                                                        | Cuándo Usarla                                                                                                                                                                                             |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `FIFTYONE_DATABASE_DIR` | Define la **ruta del disco local** donde el binario embebido de MongoDB de FiftyOne almacena sus archivos de datos (`.wt`, journals, etc.). Por defecto usa una carpeta dentro de `~/.fiftyone`. | Útil cuando se quiere aislar los datos del dataset en un disco con más espacio, o cuando se necesita resetear el estado de la base de datos eliminando solo esa carpeta sin afectar configuración global. |
| `FIFTYONE_DATABASE_URI` | Permite apuntar FiftyOne a una **instancia de MongoDB externa** (URI de conexión estándar, ej. `mongodb://usuario:password@host:27017`), en lugar de usar el binario embebido.                   | Crítico si el equipo decide centralizar el dataset en un **servidor MongoDB compartido** para que los 4 integrantes vean el mismo estado de datos en tiempo real durante la hackathon.                    |

**Ejemplo de configuración (Unix/Linux/macOS):**

```bash
export FIFTYONE_DATABASE_DIR="$HOME/.fiftyone_hackathon/db"
export FIFTYONE_DATABASE_URI="mongodb://localhost:27017"
```

**Ejemplo de configuración (PowerShell):**

```powershell
$env:FIFTYONE_DATABASE_DIR = "$HOME\.fiftyone_hackathon\db"
$env:FIFTYONE_DATABASE_URI = "mongodb://localhost:27017"
```

> 🔒 **Recomendación de equipo:** Si optan por una base de datos compartida vía `FIFTYONE_DATABASE_URI`, documenten la URI exacta (sin credenciales sensibles en texto plano dentro del repo) en un archivo `.env` ignorado por Git, y referencien solo el nombre de la variable en este documento.

---

## 4. Script de Verificación Pre-Hackathon Automatizado (Python)

El siguiente script, `verify_env.py`, debe ejecutarse en **cada máquina del equipo** antes de comenzar el desarrollo activo. Verifica de forma encadenada: versión de Python, instalación de FiftyOne, conectividad real con el backend de MongoDB (cargando un mini-dataset del Zoo), y presencia de credenciales de API necesarias para los VLMs.

```python
"""
verify_env.py
Script de verificación de entorno pre-hackathon.
Ejecutar con: python verify_env.py
"""

import os
import sys


def check_python_version():
    print("\n🔍 Verificando version de Python...")
    version_info = sys.version_info
    version_str = f"{version_info.major}.{version_info.minor}.{version_info.micro}"

    if version_info.major == 3 and version_info.minor == 11:
        print(f"✅ Python {version_str} detectado. Version correcta (3.11.x).")
        return True
    else:
        print(f"❌ ERROR: Se detecto Python {version_str}.")
        print("   Se requiere especificamente Python 3.11.x para este proyecto.")
        print("   Versiones experimentales (3.13+, 3.14) NO son compatibles con FiftyOne.")
        return False


def check_fiftyone_import():
    print("\n🔍 Verificando importacion de FiftyOne...")
    try:
        import fiftyone as fo
        print(f"✅ FiftyOne importado correctamente. Version: {fo.__version__}")
        return True, fo
    except ImportError as e:
        print("❌ ERROR: No se pudo importar 'fiftyone'.")
        print(f"   Detalle: {e}")
        print("   Solucion: pip install fiftyone")
        return False, None


def check_mongo_backend(fo_module):
    print("\n🔍 Verificando conexion con el backend de MongoDB (via FiftyOne Zoo)...")
    try:
        import fiftyone.zoo as foz

        dataset_name = "verify-env-quickstart-check"

        # Eliminar dataset previo si quedo de una corrida anterior
        if dataset_name in fo_module.list_datasets():
            fo_module.delete_dataset(dataset_name)

        dataset = foz.load_zoo_dataset(
            "quickstart",
            max_samples=5,
            dataset_name=dataset_name,
        )

        sample_count = len(dataset)

        if sample_count == 5:
            print(f"✅ Conexion con MongoDB exitosa. {sample_count} samples cargados desde el Zoo.")
            fo_module.delete_dataset(dataset_name)
            print("   (Dataset de prueba eliminado correctamente tras la verificacion)")
            return True
        else:
            print(f"⚠️  ADVERTENCIA: Se esperaban 5 samples, se obtuvieron {sample_count}.")
            return False

    except Exception as e:
        print("❌ ERROR: Fallo la conexion con el backend de MongoDB.")
        print(f"   Detalle: {e}")
        print("   Solucion: revisa la Seccion 3 de docs/01_env_setup.md")
        return False


def check_api_keys():
    print("\n🔍 Verificando variables de entorno para VLMs/Agentes...")
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if openai_key:
        print("✅ OPENAI_API_KEY detectada en el entorno.")
    else:
        print("⚠️  OPENAI_API_KEY no encontrada en el entorno.")

    if anthropic_key:
        print("✅ ANTHROPIC_API_KEY detectada en el entorno.")
    else:
        print("⚠️  ANTHROPIC_API_KEY no encontrada en el entorno.")

    if not openai_key and not anthropic_key:
        print("❌ ERROR: Ninguna API key de VLM esta configurada.")
        print("   El equipo de Vision/Brain requiere al menos una para integracion con GPT/Claude.")
        return False

    return True


def main():
    print("=" * 60)
    print(" VERIFICACION DE ENTORNO — HACKATHON VOXEL51 ")
    print("=" * 60)

    results = []

    results.append(("Version de Python", check_python_version()))

    fo_ok, fo_module = check_fiftyone_import()
    results.append(("Importacion de FiftyOne", fo_ok))

    if fo_ok:
        results.append(("Backend MongoDB / Zoo Dataset", check_mongo_backend(fo_module)))
    else:
        results.append(("Backend MongoDB / Zoo Dataset", False))

    results.append(("API Keys de VLM (OpenAI/Anthropic)", check_api_keys()))

    print("\n" + "=" * 60)
    print(" RESUMEN FINAL ")
    print("=" * 60)

    all_passed = True
    for nombre, estado in results:
        icono = "✅" if estado else "❌"
        print(f"{icono}  {nombre}")
        if not estado:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("🚀 ENTORNO LISTO. El equipo puede comenzar el desarrollo.")
    else:
        print("🛑 ENTORNO INCOMPLETO. Revisa los errores marcados arriba antes de continuar.")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
```

**Ejecución del script:**

```bash
python verify_env.py
```

> 📌 **Convención de equipo:** Este script debe ejecutarse exitosamente (`exit code 0`) antes de hacer el primer `push` a cualquier rama `feat/*`. Si el script falla, el bloqueo se resuelve **antes** de escribir código de feature.

---

## 5. Protocolo de Diagnóstico ante Fallas Comunes (Troubleshooting)

### 5.1 La Aplicación FiftyOne Crashea (Puerto 5151)

Cuando la App de FiftyOne se cierra inesperadamente o no levanta en el navegador, el primer paso es siempre **revisar los logs locales**, no reinstalar a ciegas.

```bash
# Ubicacion estandar de logs de FiftyOne
cd ~/.fiftyone/log/

# Listar los logs mas recientes
ls -lt

# Inspeccionar el log mas reciente
tail -n 100 ~/.fiftyone/log/*.log
```

**Qué buscar en el log:**

| Patrón en el log                                    | Causa probable                                        | Acción                                                     |
| --------------------------------------------------- | ----------------------------------------------------- | ---------------------------------------------------------- |
| `ConnectionFailure` / `ServerSelectionTimeoutError` | MongoDB no está corriendo o el puerto está bloqueado. | Verificar Sección 3.1 de este documento.                   |
| `Address already in use`                            | El puerto `5151` ya está ocupado por otra instancia.  | Ver Sección 5.2 a continuación.                            |
| `ModuleNotFoundError`                               | Entorno virtual incorrecto o dependencia faltante.    | Reactivar `.venv` y reinstalar con `pip install fiftyone`. |

### 5.2 Error de Puerto Ocupado (`5151` o `27017`)

Este es el error más frecuente cuando varios procesos de FiftyOne quedan corriendo en background tras cierres abruptos (Ctrl+C mal ejecutado, kernels de notebook colgados, etc.).

**Diagnóstico en Linux/macOS:**

```bash
# Identificar que proceso esta usando el puerto de la App de FiftyOne
lsof -i :5151

# Identificar que proceso esta usando el puerto de MongoDB
lsof -i :27017
```

La salida mostrará una columna `PID` (Process ID) del proceso ocupando el puerto.

**Terminar el proceso conflictivo:**

```bash
# Sustituir <PID> por el numero real obtenido de lsof
kill -9 <PID>
```

**Diagnóstico y resolución en Windows (PowerShell):**

```powershell
# Identificar el proceso usando el puerto 5151
Get-NetTCPConnection -LocalPort 5151 | Select-Object -Property OwningProcess

# Terminar el proceso usando su PID
Stop-Process -Id <PID> -Force
```

> 🔁 **Atajo de FiftyOne:** Antes de recurrir a `kill` manual, intenta primero el cierre nativo del SDK dentro de una sesión de Python:
> 
> ```python
> import fiftyone as fo
> session = fo.launch_app()
> session.close()
> ```
> 
> Esto libera el puerto `5151` de forma limpia sin necesidad de matar procesos a nivel de sistema operativo.

### 5.3 Checklist Rápido de Diagnóstico

| Síntoma                                           | Primer Comando a Ejecutar                                                                |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| La App no abre en el navegador                    | `lsof -i :5151` (Unix) / `Get-NetTCPConnection -LocalPort 5151` (Windows)                |
| Error al cargar cualquier dataset                 | `mongosh --port 27017 --eval "db.runCommand({ping:1})"`                                  |
| `ImportError` al hacer `import fiftyone`          | Confirmar entorno virtual activo: `which python` (Unix) / `Get-Command python` (Windows) |
| Comportamiento errático tras una corrida anterior | Revisar `~/.fiftyone/log/` antes de cualquier reinstalación                              |

---

## Cierre de Sección

Con este entorno validado mediante `verify_env.py`, cada integrante del equipo opera sobre una base **idéntica y reproducible**. El siguiente paso del flujo de preparación es la arquitectura del dataset: continuar en [`docs/02_dataset_architecture.md`](./02_dataset_architecture.md).
