# 🚀 docs/06_production_api.md — Orquestación Backend: API REST con FastAPI

> **Módulo 06 · Production API Layer** · Serie: _Staff-Level Technical Readiness for Data Agents & Visual Agents Hackathon (Junio 19, 2026)_
>
> **Stack confirmado:** Python 3.11 · FastAPI + Uvicorn · FiftyOne 0.23+ · MongoDB 7.0 (puerto 27017) · Puerto HTTP 8000
>
> **Dependencias de módulos anteriores que este archivo orquesta:**
> - `Módulo 03 (Brain)` → métricas de `uniqueness` y `mistakenness` precalculadas en el dataset persistente.
> - `Módulo 04 (VLM)` → pipeline asíncrono de inferencia (`asyncio.Semaphore`, `gpt-4o`, `claude-3-5-sonnet`, inyección de `fo.Classification`).
> - `Módulo 05 (MCP/Plugins)` → servidor MCP en el puerto 5152; la API REST en el 8000 es una capa **ortogonal y complementaria**, no redundante.

---

## 1. Filosofía de Desacoplamiento de la API en Hackathons

### 1.1 El problema arquitectónico central en un evento de tiempo limitado

Durante una hackathon de alta presión —especialmente una centrada en **Data Agents & Visual Agents**—, los equipos cometen de forma recurrente el mismo error de arquitectura crítico: acoplar el razonamiento del agente visual directamente al proceso del servidor FiftyOne (puerto 5151), o bien ejecutar cómputos pesados (inferencia VLM, indexación CLIP, recálculo de UMAP) de forma **síncrona y bloqueante** dentro del hilo principal del evaluador o el dashboard.

Este antipatrón produce tres patologías observables en producción de hackathon:

1. **Deadlock de recursos**: el proceso de FiftyOne App bloquea el GIL de Python mientras renderiza el dataset en el navegador. Si simultáneamente se lanza un batch de inferencia VLM sobre 500 imágenes (como hace el Módulo 04), la UI del FiftyOne App colapsa o devuelve respuestas de timeout, haciendo que los jueces no puedan visualizar el estado del agente en tiempo real.

2. **Ausencia de observabilidad externa**: un tablero de monitoreo externo (Grafana, una app Streamlit, un bot de Slack del equipo) no tiene ningún mecanismo de integración con el estado interno del proceso FiftyOne. La única forma de observar el dataset es a través de la UI embebida, que no es programable ni consultable externamente.

3. **Imposibilidad de composición multi-agente**: los agentes externos (LLM Agents de LangChain, AutoGen, o el propio Claude Code a través del servidor MCP del Módulo 05) necesitan un contrato HTTP estable para consultar el estado analítico del sistema y gatillar razonamientos visuales. Sin esta capa, el sistema es un monolito opaco.

### 1.2 La solución: Desacoplamiento mediante una capa HTTP/ASGI dedicada

La arquitectura que este módulo implementa introduce una **capa de API REST industrial** construida con **FastAPI**, corriendo bajo el servidor ASGI **Uvicorn** exclusivamente en el **puerto 8000**. Esta capa opera como un proceso Python independiente —separado del proceso FiftyOne App (5151) y del servidor MCP (5152)— y se comunica con MongoDB 7.0 (puerto 27017) a través de la API de Python de FiftyOne.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        ARQUITECTURA DE DESACOPLAMIENTO                       │
├─────────────────────────┬────────────────────────┬───────────────────────────┤
│  PROCESO 1              │  PROCESO 2             │  PROCESO 3                │
│  FiftyOne App           │  MCP Server            │  FastAPI REST API  ◄──── │
│  Puerto 5151            │  Puerto 5152           │  Puerto 8000              │
│  (Módulo 05)            │  (Módulo 05)           │  (Este módulo)            │
│                         │                        │                           │
│  UI interactiva para    │  Tool-use para Claude  │  Endpoint HTTP para       │
│  anotadores humanos     │  Code / Cursor         │  dashboards, bots,        │
│                         │                        │  agentes externos y CI/CD │
├─────────────────────────┴────────────────────────┴───────────────────────────┤
│                    CAPA DE PERSISTENCIA COMPARTIDA                           │
│              MongoDB 7.0 · Puerto 27017 · Dataset "hackathon-dataset"        │
│         (FiftyOne escribe / Los tres procesos leen concurrentemente)         │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Beneficios arquitectónicos concretos de esta separación

**a) Eliminación de colas de bloqueo síncronas bajo presión de tiempo:**

FastAPI es un framework ASGI (Asynchronous Server Gateway Interface) nativo. Esto significa que puede manejar múltiples requests HTTP concurrentes sin necesitar threads adicionales para I/O bound operations. Cuando un agente externo solicita `GET /api/v1/dataset/summary` mientras simultáneamente se está ejecutando un `POST /api/v1/agent/audit` que lanzó un batch VLM de larga duración en background, FastAPI despacha ambas corrutinas en el mismo event loop de `asyncio` sin bloqueo mutuo. La clave técnica es el uso de `BackgroundTasks` de FastAPI para el endpoint de auditoría: la tarea pesada se encola en background y el endpoint retorna inmediatamente con HTTP 202, liberando el event loop para otras solicitudes entrantes.

**b) Comunicación fluida con tableros externos:**

El contrato REST que este módulo expone es consumible desde cualquier cliente HTTP: una aplicación Streamlit que presente métricas en tiempo real a los jueces, un bot de Slack que notifique cuando el índice de mistakenness supera un umbral crítico, un dashboard de Grafana con el plugin JSON API, o un script de monitoreo en CI/CD que decida si el dataset es apto para inferencia según el `uniqueness` promedio. Ninguno de estos clientes necesita conocer FiftyOne, Python, ni MongoDB. Solo necesitan HTTP y JSON.

**c) Desacoplamiento del ciclo de vida del VLM pipeline:**

El pipeline del Módulo 04 (`asyncio.Semaphore`, inferencia `gpt-4o` / `claude-3-5-sonnet`, parseo de JSON estructurado, inyección de `fo.Classification`) es un componente de alto costo computacional y latencia variable (dependiente de la API de OpenAI/Anthropic). Envolver este pipeline detrás de un endpoint `POST /api/v1/agent/audit` con respuesta HTTP 202 y procesamiento en `BackgroundTasks` significa que el cliente nunca queda bloqueado esperando la respuesta de un LLM externo. El cliente recibe un `job_id` de tracking inmediatamente y puede consultar el estado del dataset posteriormente via `GET /api/v1/dataset/summary`.

**d) Trazabilidad y auditoría del agente visual:**

Cada request al endpoint REST puede ser logeado con un request ID único (UUID4), el timestamp de ingreso, la vista solicitada, el proveedor VLM seleccionado y el resultado HTTP. Esto crea un registro de auditoría del comportamiento del agente visual que es completamente independiente del log interno de FiftyOne, facilitando el debugging post-mortem y la demostración de trazabilidad ante los jueces de la hackathon.

---

## 2. Gestión del Ciclo de Vida de FiftyOne dentro del Servidor ASGI

### 2.1 El problema del estado global en procesos ASGI

FiftyOne mantiene una referencia al dataset activo como un objeto Python en memoria (`fo.Dataset`). En un servidor ASGI como Uvicorn/FastAPI, este objeto debe ser inicializado **exactamente una vez** durante el arranque del proceso y debe ser accesible de forma thread-safe desde cualquier endpoint handler. El patrón incorrecto —instanciar `fo.load_dataset()` dentro de cada función de endpoint— introduce latencia de reconexión a MongoDB en cada request y puede crear race conditions durante cargas concurrentes.

La solución correcta es utilizar el mecanismo de **lifespan context manager** de FastAPI (introducido en FastAPI 0.93.0 y recomendado sobre los decoradores `@app.on_event` que están marcados como deprecated en versiones recientes del framework), combinado con una variable de estado global que se inicializa durante el startup y se limpia durante el shutdown.

### 2.2 Código de orquestación defensivo del ciclo de vida

El siguiente bloque de código implementa el ciclo de vida completo con verificación de integridad, manejo de errores descriptivo y logging estructurado. Este es el bloque fundacional que debe estar presente en el script antes de cualquier definición de endpoint.

```python
# ============================================================================
# api/lifecycle.py
# Gestión defensiva del ciclo de vida de FiftyOne dentro del proceso ASGI.
# Separado en módulo propio para permitir testeo unitario independiente.
# ============================================================================

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import fiftyone as fo
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Configuración del logger estructurado a nivel de módulo.
# Utilizamos el mismo nombre de logger que el módulo raíz de la aplicación
# para que la jerarquía de logging sea coherente en todos los módulos.
# ---------------------------------------------------------------------------
logger = logging.getLogger("hackathon_api.lifecycle")

# ---------------------------------------------------------------------------
# CONSTANTE: Nombre canónico del dataset persistido en MongoDB.
# Esta constante DEBE coincidir con la utilizada en todos los módulos
# anteriores (01 al 05) para garantizar el acoplamiento milimétrico del sistema.
# ---------------------------------------------------------------------------
DATASET_NAME: str = "hackathon-dataset"

# ---------------------------------------------------------------------------
# Estado global del servidor.
# Se accede mediante la variable de módulo `app_state` desde los endpoints.
# No se utiliza `app.state` de FastAPI directamente para mantener la
# compatibilidad con testeo fuera del contexto de la aplicación HTTP.
# ---------------------------------------------------------------------------
app_state: dict = {
    "dataset": None,          # fo.Dataset activo tras el startup
    "dataset_ready": False,   # Flag booleano de disponibilidad
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Context manager de ciclo de vida ASGI para la aplicación FastAPI.

    Implementa el patrón recomendado por FastAPI 0.93+ en sustitución de
    los decoradores deprecated @app.on_event('startup') y @app.on_event('shutdown').

    El contexto ejecuta el bloque ANTES del yield durante el arranque del servidor
    (startup phase) y el bloque DESPUÉS del yield durante el apagado (shutdown phase).

    Raises:
        SystemExit: Si el dataset no puede ser cargado o verificado durante
                    el startup. El proceso ASGI NO debe arrancar con un estado
                    inválido del dataset: fallar rápido es la decisión correcta.
    """
    # -----------------------------------------------------------------------
    # FASE DE STARTUP
    # -----------------------------------------------------------------------
    logger.info("=" * 70)
    logger.info("STARTUP · Inicializando capa API REST de FiftyOne")
    logger.info("=" * 70)

    try:
        # -------------------------------------------------------------------
        # PASO 1: Verificar que FiftyOne puede listar los datasets existentes.
        # Esta llamada valida la conectividad con MongoDB en el puerto 27017.
        # Si MongoDB no está disponible, fo.list_datasets() lanzará una
        # excepción de conexión que capturamos para proporcionar un mensaje
        # de error descriptivo en lugar de un traceback genérico.
        # -------------------------------------------------------------------
        logger.info(f"Verificando conectividad con MongoDB (puerto 27017)...")
        available_datasets = fo.list_datasets()
        logger.info(f"MongoDB OK. Datasets disponibles: {available_datasets}")

        # -------------------------------------------------------------------
        # PASO 2: Verificar que el dataset objetivo existe en la base de datos.
        # Un dataset puede ser listado pero aún así estar en estado corrupto
        # si su metadata en MongoDB está incompleta. Por eso verificamos
        # la presencia antes de intentar la carga.
        # -------------------------------------------------------------------
        if DATASET_NAME not in available_datasets:
            logger.critical(
                f"STARTUP FAILURE: El dataset '{DATASET_NAME}' no existe en MongoDB. "
                f"Datasets disponibles: {available_datasets}. "
                f"Ejecuta el Módulo 01 (setup) para crear e inicializar el dataset."
            )
            sys.exit(1)

        # -------------------------------------------------------------------
        # PASO 3: Cargar el dataset con verificación de persistencia.
        # fo.load_dataset() lanza fo.core.dataset.DatasetNotFoundError si el
        # dataset no existe, pero dado que ya verificamos la presencia en el
        # paso anterior, aquí el error más probable es una corrupción de
        # metadata en MongoDB, que también capturamos.
        # -------------------------------------------------------------------
        logger.info(f"Cargando dataset '{DATASET_NAME}' desde MongoDB...")
        dataset: fo.Dataset = fo.load_dataset(DATASET_NAME)

        # -------------------------------------------------------------------
        # PASO 4: Verificar la integridad mínima del dataset.
        # Un dataset válido para este sistema debe:
        # (a) tener al menos una muestra,
        # (b) ser persistente (persistent=True garantiza que MongoDB conserva
        #     el estado entre reinicios del servidor API).
        # -------------------------------------------------------------------
        sample_count: int = len(dataset)
        if sample_count == 0:
            logger.warning(
                f"STARTUP WARNING: El dataset '{DATASET_NAME}' existe pero está vacío "
                f"(0 muestras). Los endpoints de auditoría retornarán resultados vacíos. "
                f"Esto puede ser intencional en un entorno de CI/CD, continuando..."
            )

        # -------------------------------------------------------------------
        # PASO 5: Garantizar la persistencia transaccional.
        # Si por alguna razón el dataset fue creado en sesión efímera
        # (persistent=False), lo convertimos a persistente aquí para
        # evitar la pérdida de datos cuando el servidor se reinicie.
        # -------------------------------------------------------------------
        if not dataset.persistent:
            logger.warning(
                f"El dataset '{DATASET_NAME}' NO es persistente. "
                f"Estableciendo persistent=True para garantizar durabilidad en MongoDB..."
            )
            dataset.persistent = True
            logger.info(f"Persistencia garantizada. Dataset '{DATASET_NAME}' ahora es persistente.")

        # -------------------------------------------------------------------
        # PASO 6: Registrar el dataset en el estado global del servidor.
        # -------------------------------------------------------------------
        app_state["dataset"] = dataset
        app_state["dataset_ready"] = True

        logger.info(
            f"STARTUP OK · Dataset '{DATASET_NAME}' cargado exitosamente. "
            f"Muestras totales: {sample_count}. "
            f"Campos del schema: {list(dataset.get_field_schema().keys())}. "
            f"Servidor API listo en http://0.0.0.0:8000"
        )
        logger.info("=" * 70)

    except Exception as e:
        logger.critical(
            f"STARTUP FAILURE: Error irrecuperable durante la inicialización "
            f"del dataset FiftyOne: {type(e).__name__}: {e}. "
            f"El servidor NO arrancará. Revisa la conexión a MongoDB y el Módulo 01.",
            exc_info=True,
        )
        sys.exit(1)

    # -----------------------------------------------------------------------
    # PUNTO DE YIELD: El servidor está vivo y procesando requests HTTP.
    # Todo el código anterior al yield es el STARTUP.
    # Todo el código posterior al yield es el SHUTDOWN.
    # -----------------------------------------------------------------------
    yield

    # -----------------------------------------------------------------------
    # FASE DE SHUTDOWN
    # Limpieza ordenada de recursos. FiftyOne no requiere cierre explícito
    # de conexión (es gestionado por el driver de pymongo), pero establecemos
    # el flag de disponibilidad a False para que cualquier request en vuelo
    # durante el shutdown reciba un error descriptivo en lugar de un NPE.
    # -----------------------------------------------------------------------
    logger.info("=" * 70)
    logger.info("SHUTDOWN · Cerrando capa API REST de FiftyOne")
    app_state["dataset_ready"] = False
    app_state["dataset"] = None
    logger.info("SHUTDOWN OK · Estado del servidor limpiado. Conexión MongoDB cerrada por pymongo.")
    logger.info("=" * 70)
```

### 2.3 Nota sobre compatibilidad con `@app.on_event` (legacy)

Si el entorno de la hackathon tiene una versión de FastAPI anterior a 0.93.0 (verificable con `pip show fastapi`), el patrón `lifespan` no está disponible. En ese caso, el equivalente funcional usando los decoradores legacy es el siguiente. **No mezclar ambos patrones en el mismo script**: son mutuamente excluyentes.

```python
# ALTERNATIVA LEGACY: Solo si FastAPI < 0.93.0
# En versiones modernas, usar el patrón lifespan del bloque anterior.

@app.on_event("startup")
async def startup_event() -> None:
    """Equivalente legacy del bloque de startup del lifespan context manager."""
    # ... mismo código del bloque try anterior ...
    pass


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Equivalente legacy del bloque de shutdown del lifespan context manager."""
    app_state["dataset_ready"] = False
    app_state["dataset"] = None
    logger.info("SHUTDOWN OK (legacy event handler)")
```

---

## 3. Construcción de Endpoints de Producción (Código Completo)

### 3.1 Estructura del script completo

El siguiente es el script Python completo, autocontenido, tipado estrictamente con Pydantic v2 y hiper-documentado. Está diseñado para ser guardado como `api/main.py` en la raíz del repositorio de la hackathon.

```python
# ============================================================================
# api/main.py
# Capa de API REST industrial para el sistema FiftyOne Visual Agent.
# Hackathon: Data Agents & Visual Agents · Junio 19, 2026
#
# RESPONSABILIDADES DE ESTE MÓDULO:
#   - Exponer el estado analítico del dataset FiftyOne via HTTP/JSON
#   - Gatillar el pipeline de inferencia VLM asíncrono (Módulo 04)
#     de forma no bloqueante mediante BackgroundTasks de FastAPI
#   - Gestionar el ciclo de vida del proceso ASGI con verificación
#     defensiva de la conectividad a MongoDB
#
# PUERTOS DEL SISTEMA:
#   - Este servidor: 8000 (HTTP REST API)
#   - FiftyOne App: 5151 (UI interactiva)
#   - MCP Server: 5152 (tool-use para Claude Code / Cursor)
#   - MongoDB: 27017 (persistencia del dataset)
#
# DEPENDENCIAS DIRECTAS:
#   - fastapi >= 0.93.0
#   - uvicorn[standard] >= 0.23.0
#   - fiftyone >= 0.23.0
#   - pydantic >= 2.0.0
#   - python >= 3.11
#
# USO:
#   uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
# ============================================================================

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

import fiftyone as fo
import fiftyone.brain as fob
from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# IMPORTACIÓN DEL PIPELINE VLM (Módulo 04)
# El módulo 04 expone `run_vlm_audit_pipeline`, una función async que recibe
# una `fo.DatasetView` y un proveedor VLM, y ejecuta inferencia asíncrona
# controlada por asyncio.Semaphore, inyectando fo.Classification en cada
# muestra antes de llamar a sample.save().
#
# NOTA: Si ejecutas este script de forma standalone sin el Módulo 04,
# reemplaza esta importación por un stub:
#   async def run_vlm_audit_pipeline(view, provider, confidence_threshold): pass
# ---------------------------------------------------------------------------
try:
    from vlm.pipeline import run_vlm_audit_pipeline  # Módulo 04
except ImportError:
    # Stub defensivo para entornos donde el Módulo 04 no está montado.
    # Permite que el servidor arranque y responda a consultas de summary
    # incluso cuando el pipeline VLM no está disponible.
    import warnings
    warnings.warn(
        "ADVERTENCIA: No se pudo importar 'vlm.pipeline.run_vlm_audit_pipeline'. "
        "El endpoint POST /api/v1/agent/audit usará un stub no-operativo. "
        "Asegúrate de que el Módulo 04 esté correctamente instalado.",
        ImportWarning,
        stacklevel=2,
    )

    async def run_vlm_audit_pipeline(
        view: fo.DatasetView,
        provider: str,
        confidence_threshold: float,
    ) -> None:
        """Stub no-operativo del pipeline VLM para entornos sin Módulo 04."""
        logger.warning(
            f"STUB EJECUTADO: run_vlm_audit_pipeline(provider={provider}, "
            f"confidence_threshold={confidence_threshold}). "
            f"No se procesaron muestras. Instala el Módulo 04."
        )


# ============================================================================
# CONFIGURACIÓN DEL SISTEMA DE LOGGING
# Utilizamos basicConfig para garantizar que el logging esté disponible
# desde el primer momento del startup, antes de que FastAPI inicialice
# su propio middleware de logging.
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s · %(name)s · %(levelname)s · %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("hackathon_api")

# ============================================================================
# CONSTANTES DEL SISTEMA
# ============================================================================
DATASET_NAME: str = "hackathon-dataset"
API_VERSION: str = "v1"
API_PREFIX: str = f"/api/{API_VERSION}"

# Proveedores VLM soportados (deben coincidir con los del Módulo 04)
SUPPORTED_VLM_PROVIDERS: set[str] = {"gpt-4o", "claude-3-5-sonnet"}

# ============================================================================
# ESTADO GLOBAL DEL SERVIDOR
# ============================================================================
app_state: dict[str, Any] = {
    "dataset": None,
    "dataset_ready": False,
}


# ============================================================================
# CICLO DE VIDA DEL SERVIDOR ASGI
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Context manager de ciclo de vida ASGI.

    Gestiona el startup y shutdown del servidor de forma atómica y defensiva.
    Ver Sección 2 de este documento para la explicación arquitectónica completa.
    """
    import sys

    logger.info("=" * 70)
    logger.info("STARTUP · API REST FiftyOne Visual Agent")
    logger.info(f"          Dataset objetivo: '{DATASET_NAME}'")
    logger.info(f"          Puerto HTTP: 8000")
    logger.info("=" * 70)

    try:
        # --- Verificar conectividad MongoDB ---
        logger.info("Verificando conectividad con MongoDB (localhost:27017)...")
        available_datasets = fo.list_datasets()
        logger.info(f"MongoDB conectado. Datasets en base de datos: {available_datasets}")

        # --- Verificar existencia del dataset ---
        if DATASET_NAME not in available_datasets:
            logger.critical(
                f"STARTUP FAILURE: Dataset '{DATASET_NAME}' no encontrado. "
                f"Ejecuta el Módulo 01 para crear el dataset."
            )
            sys.exit(1)

        # --- Cargar el dataset desde MongoDB ---
        logger.info(f"Cargando dataset '{DATASET_NAME}'...")
        dataset: fo.Dataset = fo.load_dataset(DATASET_NAME)
        sample_count: int = len(dataset)

        if sample_count == 0:
            logger.warning(
                f"Dataset '{DATASET_NAME}' cargado pero vacío (0 muestras). "
                f"Las métricas del endpoint summary estarán en estado inicial."
            )

        # --- Garantizar persistencia transaccional ---
        if not dataset.persistent:
            logger.warning(
                f"Dataset '{DATASET_NAME}' no es persistente. "
                f"Estableciendo persistent=True..."
            )
            dataset.persistent = True

        # --- Registrar en estado global ---
        app_state["dataset"] = dataset
        app_state["dataset_ready"] = True

        logger.info(
            f"STARTUP OK · Dataset '{DATASET_NAME}' listo. "
            f"Muestras: {sample_count}. "
            f"Schema: {list(dataset.get_field_schema().keys())}."
        )
        logger.info("=" * 70)

    except SystemExit:
        raise
    except Exception as exc:
        logger.critical(
            f"STARTUP FAILURE: {type(exc).__name__}: {exc}",
            exc_info=True,
        )
        sys.exit(1)

    # --- El servidor está activo ---
    yield

    # --- SHUTDOWN ---
    logger.info("SHUTDOWN · Limpiando estado del servidor...")
    app_state["dataset_ready"] = False
    app_state["dataset"] = None
    logger.info("SHUTDOWN OK · Servidor detenido limpiamente.")


# ============================================================================
# INSTANCIA DE LA APLICACIÓN FASTAPI
# ============================================================================
app = FastAPI(
    title="FiftyOne Visual Agent REST API",
    description=(
        "Capa de API REST industrial para exponer el estado analítico del "
        "dataset FiftyOne y gatillar el razonamiento del agente visual "
        "de forma asíncrona y no bloqueante. "
        "Hackathon: Data Agents & Visual Agents · Junio 19, 2026."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",           # Swagger UI disponible en http://localhost:8000/docs
    redoc_url="/redoc",         # ReDoc disponible en http://localhost:8000/redoc
    openapi_url="/openapi.json",
)


# ============================================================================
# MODELOS PYDANTIC V2: SCHEMAS DE REQUEST Y RESPONSE
# ============================================================================

class DatasetSummaryResponse(BaseModel):
    """
    Schema de respuesta para el endpoint GET /api/v1/dataset/summary.

    Encapsula el estado analítico completo del dataset FiftyOne, incluyendo
    métricas precalculadas por los módulos Brain (03) y VLM (04).
    """

    # Identificadores del dataset
    dataset_name: str = Field(
        ...,
        description="Nombre canónico del dataset en MongoDB.",
        examples=["hackathon-dataset"],
    )
    total_samples: int = Field(
        ...,
        ge=0,
        description="Número total de muestras en el dataset completo (sin filtros).",
        examples=[1247],
    )

    # Metadata del schema
    field_schema: dict[str, str] = Field(
        ...,
        description=(
            "Diccionario de campos detectados en el schema del dataset. "
            "Clave: nombre del campo. Valor: tipo FiftyOne serializado como string."
        ),
        examples=[{"filepath": "StringField", "ground_truth": "EmbeddedDocumentField", "uniqueness": "FloatField"}],
    )

    # Clases de etiquetas
    label_classes: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Clases únicas de etiquetas detectadas por campo. "
            "Clave: nombre del campo de label. Valor: lista de clases únicas."
        ),
        examples=[{"ground_truth": ["cat", "dog", "bird"], "vlm_audit": ["correct", "incorrect", "uncertain"]}],
    )

    # Métricas Brain (Módulo 03)
    avg_uniqueness: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Promedio de la métrica 'uniqueness' calculada por fiftyone.brain "
            "en el Módulo 03. Rango [0.0, 1.0]. None si la métrica no ha sido calculada."
        ),
        examples=[0.73],
    )
    avg_mistakenness: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Promedio de la métrica 'mistakenness' calculada por fob.compute_mistakenness "
            "en el Módulo 03. Rango [0.0, 1.0]. None si la métrica no ha sido calculada."
        ),
        examples=[0.12],
    )

    # Vistas guardadas disponibles
    saved_views: list[str] = Field(
        default_factory=list,
        description=(
            "Lista de nombres de vistas guardadas (saved views) disponibles en el dataset. "
            "Estos nombres son los válidos para usar en el campo 'saved_view_name' "
            "del endpoint POST /api/v1/agent/audit."
        ),
        examples=[["high_uniqueness", "mistaken_labels", "audit_subset_50"]],
    )

    # Metadata de la respuesta
    generated_at: str = Field(
        ...,
        description="Timestamp ISO 8601 UTC del momento en que se generó esta respuesta.",
        examples=["2026-06-19T14:32:01Z"],
    )


class AgentAuditRequest(BaseModel):
    """
    Schema de request para el endpoint POST /api/v1/agent/audit.

    Define los parámetros necesarios para lanzar un batch de auditoría
    asíncrona mediante el pipeline VLM del Módulo 04.
    """

    saved_view_name: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description=(
            "Nombre de la vista guardada (saved view) en FiftyOne sobre la cual "
            "se ejecutará el pipeline de auditoría VLM. "
            "Debe existir en el dataset. Consulta GET /api/v1/dataset/summary "
            "para obtener la lista de vistas disponibles."
        ),
        examples=["high_uniqueness"],
    )
    vlm_provider: str = Field(
        ...,
        description=(
            "Proveedor del modelo de lenguaje visual (VLM) a utilizar para la auditoría. "
            f"Valores válidos: {sorted(SUPPORTED_VLM_PROVIDERS)}."
        ),
        examples=["gpt-4o"],
    )
    confidence_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description=(
            "Umbral de confianza mínimo [0.0, 1.0] para que una predicción VLM "
            "sea inyectada como fo.Classification en el dataset. "
            "Predicciones con confianza inferior a este umbral serán marcadas "
            "como 'uncertain' en lugar de la clase predicha."
        ),
        examples=[0.75],
    )

    @field_validator("vlm_provider")
    @classmethod
    def validate_vlm_provider(cls, v: str) -> str:
        """
        Valida que el proveedor VLM sea uno de los soportados por el Módulo 04.

        Raises:
            ValueError: Si el proveedor no está en SUPPORTED_VLM_PROVIDERS.
        """
        if v not in SUPPORTED_VLM_PROVIDERS:
            raise ValueError(
                f"Proveedor VLM '{v}' no soportado. "
                f"Proveedores válidos: {sorted(SUPPORTED_VLM_PROVIDERS)}."
            )
        return v


class AgentAuditResponse(BaseModel):
    """
    Schema de respuesta para el endpoint POST /api/v1/agent/audit.

    Retornado inmediatamente con HTTP 202 Accepted.
    El procesamiento real ocurre en background de forma asíncrona.
    """

    status: str = Field(
        default="accepted",
        description="Estado del job. Siempre 'accepted' en la respuesta HTTP 202.",
    )
    job_id: str = Field(
        ...,
        description=(
            "Identificador único del job de auditoría (UUID4). "
            "Puede utilizarse para correlacionar logs del servidor con este request específico."
        ),
        examples=["f47ac10b-58cc-4372-a567-0e02b2c3d479"],
    )
    message: str = Field(
        ...,
        description="Mensaje descriptivo del estado del job para consumo humano.",
    )
    saved_view_name: str = Field(
        ...,
        description="Nombre de la vista guardada que será procesada por el pipeline VLM.",
    )
    vlm_provider: str = Field(
        ...,
        description="Proveedor VLM que ejecutará la inferencia.",
    )
    confidence_threshold: float = Field(
        ...,
        description="Umbral de confianza mínimo aplicado al pipeline de inferencia.",
    )
    accepted_at: str = Field(
        ...,
        description="Timestamp ISO 8601 UTC del momento de aceptación del job.",
    )
    tracking_hint: str = Field(
        ...,
        description=(
            "Instrucción para el cliente sobre cómo monitorear el progreso del job. "
            "El estado del procesamiento puede consultarse via GET /api/v1/dataset/summary "
            "una vez que el job haya completado."
        ),
    )


# ============================================================================
# FUNCIONES AUXILIARES INTERNAS
# ============================================================================

def _get_dataset() -> fo.Dataset:
    """
    Función auxiliar defensiva para obtener el dataset activo del estado global.

    Encapsula la verificación de disponibilidad del dataset en un punto único
    de verdad, evitando duplicación de lógica de validación en cada endpoint.

    Returns:
        fo.Dataset: El dataset activo cargado durante el startup.

    Raises:
        HTTPException(503): Si el dataset no está disponible (startup incompleto
                            o servidor en proceso de shutdown).
    """
    if not app_state.get("dataset_ready") or app_state.get("dataset") is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "El dataset FiftyOne no está disponible en este momento. "
                "El servidor puede estar en proceso de inicialización o shutdown. "
                "Reintenta en unos segundos. Si el problema persiste, verifica "
                "que MongoDB esté corriendo en localhost:27017 y que el dataset "
                f"'{DATASET_NAME}' exista (ejecuta el Módulo 01)."
            ),
        )
    return app_state["dataset"]


def _compute_field_schema(dataset: fo.Dataset) -> dict[str, str]:
    """
    Extrae y serializa el schema de campos del dataset FiftyOne como dict JSON-serializable.

    FiftyOne retorna instancias de subclases de `fo.Field` que no son directamente
    serializables por Pydantic. Esta función las convierte a sus nombres de tipo
    como strings.

    Args:
        dataset: Dataset FiftyOne activo.

    Returns:
        dict[str, str]: Mapeo de nombre de campo → tipo de campo como string.
    """
    raw_schema = dataset.get_field_schema()
    return {
        field_name: type(field_obj).__name__
        for field_name, field_obj in raw_schema.items()
    }


def _extract_label_classes(dataset: fo.Dataset) -> dict[str, list[str]]:
    """
    Detecta y extrae las clases únicas de etiquetas de todos los campos
    de tipo Label en el dataset.

    Itera sobre el schema del dataset, identifica los campos que son subclases
    de `fo.Label` (Classification, Detections, Segmentation, etc.), y extrae
    los valores únicos del campo `label` de cada uno.

    Args:
        dataset: Dataset FiftyOne activo.

    Returns:
        dict[str, list[str]]: Mapeo de nombre de campo → lista de clases únicas ordenadas.
                              Campos sin etiquetas o con valores nulos son excluidos.
    """
    label_classes: dict[str, list[str]] = {}
    schema = dataset.get_field_schema()

    for field_name, field_obj in schema.items():
        field_type_name = type(field_obj).__name__

        # FiftyOne representa campos de etiquetas como EmbeddedDocumentField
        # cuyo `document_type` es una subclase de fo.Label.
        if field_type_name == "EmbeddedDocumentField":
            try:
                doc_type = field_obj.document_type
                if doc_type is not None and issubclass(doc_type, fo.Label):
                    # Para Classification, el campo de clase es 'label'
                    # Para Detections, necesitamos ir al nivel de detección
                    distinct_values = dataset.distinct(f"{field_name}.label")
                    if distinct_values:
                        label_classes[field_name] = sorted(
                            [str(v) for v in distinct_values if v is not None]
                        )
            except (AttributeError, TypeError, Exception):
                # Si el campo no tiene document_type o no es un Label,
                # lo ignoramos silenciosamente.
                continue

    return label_classes


def _compute_metric_average(dataset: fo.Dataset, field_name: str) -> Optional[float]:
    """
    Calcula el promedio de una métrica numérica en el dataset FiftyOne.

    Utiliza `dataset.mean()` de FiftyOne que ejecuta la agregación directamente
    en MongoDB, evitando cargar todos los valores en memoria.

    Args:
        dataset: Dataset FiftyOne activo.
        field_name: Nombre del campo numérico cuyo promedio se quiere calcular.
                    Por ejemplo: 'uniqueness', 'mistakenness'.

    Returns:
        float: Promedio del campo, redondeado a 6 decimales.
        None: Si el campo no existe en el schema o si todos los valores son None.
    """
    try:
        schema = dataset.get_field_schema()
        if field_name not in schema:
            return None

        result = dataset.mean(field_name)
        if result is None:
            return None

        return round(float(result), 6)

    except Exception as exc:
        logger.warning(
            f"No se pudo calcular el promedio de '{field_name}': "
            f"{type(exc).__name__}: {exc}. Retornando None."
        )
        return None


async def _execute_vlm_audit_in_background(
    view: fo.DatasetView,
    provider: str,
    confidence_threshold: float,
    job_id: str,
) -> None:
    """
    Wrapper async del pipeline VLM del Módulo 04 para ejecución en BackgroundTask.

    Encapsula el pipeline de inferencia en un bloque try/except para garantizar
    que cualquier error en el pipeline VLM sea logeado con el job_id de tracking
    pero no propague excepciones que puedan afectar el proceso ASGI principal.

    Args:
        view: Vista FiftyOne sobre la que se ejecutará la inferencia.
        provider: Proveedor VLM ('gpt-4o' o 'claude-3-5-sonnet').
        confidence_threshold: Umbral de confianza mínimo [0.0, 1.0].
        job_id: UUID4 de tracking para correlación en logs.
    """
    logger.info(
        f"[JOB {job_id}] BACKGROUND START · "
        f"Provider: {provider} · "
        f"Muestras en vista: {len(view)} · "
        f"Confidence threshold: {confidence_threshold}"
    )
    start_time = datetime.now(timezone.utc)

    try:
        await run_vlm_audit_pipeline(
            view=view,
            provider=provider,
            confidence_threshold=confidence_threshold,
        )
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(
            f"[JOB {job_id}] BACKGROUND COMPLETE · "
            f"Tiempo de ejecución: {elapsed:.2f}s. "
            f"Los resultados ya están disponibles en GET /api/v1/dataset/summary."
        )
    except Exception as exc:
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.error(
            f"[JOB {job_id}] BACKGROUND FAILURE · "
            f"Error después de {elapsed:.2f}s: "
            f"{type(exc).__name__}: {exc}",
            exc_info=True,
        )


# ============================================================================
# ENDPOINT 1: GET /api/v1/dataset/summary
# ============================================================================

@app.get(
    path=f"{API_PREFIX}/dataset/summary",
    response_model=DatasetSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Resumen analítico completo del dataset FiftyOne",
    description=(
        "Inspecciona dinámicamente el dataset FiftyOne activo y retorna un JSON estructurado "
        "con el estado analítico completo: total de muestras, schema de campos detectados, "
        "clases únicas de etiquetas por campo, y métricas promedio precalculadas por el "
        "Módulo Brain (uniqueness, mistakenness). "
        "También incluye la lista de vistas guardadas disponibles para usar en "
        "POST /api/v1/agent/audit."
    ),
    tags=["Dataset Analytics"],
    responses={
        200: {
            "description": "Estado analítico del dataset retornado exitosamente.",
        },
        503: {
            "description": (
                "El dataset FiftyOne no está disponible. "
                "El servidor puede estar iniciando o MongoDB no está accesible."
            ),
        },
    },
)
async def get_dataset_summary() -> DatasetSummaryResponse:
    """
    Endpoint de consulta analítica del estado completo del dataset FiftyOne.

    Este endpoint es el punto de entrada principal para cualquier cliente externo
    que necesite conocer el estado del sistema antes de lanzar una auditoría VLM.
    Ejecuta todas sus operaciones de consulta a MongoDB de forma síncrona pero
    eficiente mediante las APIs de agregación de FiftyOne que delegan el cómputo
    al motor de MongoDB.

    Returns:
        DatasetSummaryResponse: JSON con el estado analítico completo del dataset.

    Raises:
        HTTPException(503): Si el dataset no está disponible en el estado global.
        HTTPException(500): Si ocurre un error inesperado durante la consulta.
    """
    # --- Obtener dataset activo de forma defensiva ---
    dataset: fo.Dataset = _get_dataset()

    try:
        # --- Recopilar métricas del dataset ---
        logger.info("GET /summary · Calculando métricas del dataset...")

        # Total de muestras (operación O(1) en FiftyOne, cached en metadata)
        total_samples: int = len(dataset)

        # Schema de campos (delegado a MongoDB)
        field_schema: dict[str, str] = _compute_field_schema(dataset)

        # Clases únicas de etiquetas (distinct query en MongoDB)
        label_classes: dict[str, list[str]] = _extract_label_classes(dataset)

        # Métricas Brain: uniqueness y mistakenness (mean aggregation en MongoDB)
        avg_uniqueness: Optional[float] = _compute_metric_average(dataset, "uniqueness")
        avg_mistakenness: Optional[float] = _compute_metric_average(dataset, "mistakenness")

        # Vistas guardadas disponibles
        saved_views: list[str] = dataset.list_saved_views()

        # Timestamp de generación de la respuesta
        generated_at: str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        response = DatasetSummaryResponse(
            dataset_name=DATASET_NAME,
            total_samples=total_samples,
            field_schema=field_schema,
            label_classes=label_classes,
            avg_uniqueness=avg_uniqueness,
            avg_mistakenness=avg_mistakenness,
            saved_views=saved_views,
            generated_at=generated_at,
        )

        logger.info(
            f"GET /summary · OK · "
            f"Muestras: {total_samples} · "
            f"Campos: {len(field_schema)} · "
            f"avg_uniqueness: {avg_uniqueness} · "
            f"avg_mistakenness: {avg_mistakenness}"
        )
        return response

    except HTTPException:
        # Re-lanzar HTTPExceptions sin envolver (ya son descriptivas)
        raise
    except Exception as exc:
        logger.error(
            f"GET /summary · ERROR INESPERADO: {type(exc).__name__}: {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Error interno al calcular el resumen del dataset '{DATASET_NAME}'. "
                f"Tipo de error: {type(exc).__name__}. "
                f"Revisa los logs del servidor para el stack trace completo."
            ),
        )


# ============================================================================
# ENDPOINT 2: POST /api/v1/agent/audit
# ============================================================================

@app.post(
    path=f"{API_PREFIX}/agent/audit",
    response_model=AgentAuditResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Lanzar auditoría asíncrona del agente visual sobre una vista guardada",
    description=(
        "Recibe los parámetros de configuración de la auditoría VLM (vista guardada, "
        "proveedor VLM, umbral de confianza), valida la existencia de la vista en el "
        "dataset FiftyOne, y lanza el pipeline de inferencia asíncrono del Módulo 04 "
        "como BackgroundTask de FastAPI. "
        "Retorna inmediatamente con HTTP 202 Accepted y un job_id de tracking, "
        "sin bloquear el event loop del servidor. "
        "El progreso puede monitorearse consultando GET /api/v1/dataset/summary "
        "una vez que el pipeline haya completado."
    ),
    tags=["Visual Agent"],
    responses={
        202: {
            "description": (
                "Job de auditoría aceptado y encolado en background. "
                "El procesamiento VLM ocurre de forma asíncrona."
            ),
        },
        400: {
            "description": (
                "Request inválido. La vista guardada no existe en el dataset, "
                "o los parámetros de request no son válidos."
            ),
        },
        422: {
            "description": (
                "Error de validación Pydantic. El proveedor VLM no es válido, "
                "o el umbral de confianza está fuera del rango [0.0, 1.0]."
            ),
        },
        503: {
            "description": "El dataset FiftyOne no está disponible.",
        },
    },
)
async def post_agent_audit(
    request_body: AgentAuditRequest,
    background_tasks: BackgroundTasks,
) -> AgentAuditResponse:
    """
    Endpoint de gatillado del agente visual para auditoría asíncrona.

    Diseñado para escenarios donde el cliente (un agente LLM, un dashboard,
    un bot de monitoreo) necesita lanzar un batch de inferencia VLM sobre
    un subconjunto específico del dataset sin esperar a que el procesamiento
    complete antes de recibir una respuesta HTTP.

    El patrón BackgroundTasks de FastAPI garantiza que el job VLM se ejecuta
    en el mismo event loop de asyncio que el servidor, sin crear threads
    adicionales, aprovechando el pipeline asyncio.Semaphore del Módulo 04.

    Args:
        request_body: Parámetros de la auditoría (vista, proveedor, umbral).
        background_tasks: Gestor de tareas en background de FastAPI (inyectado).

    Returns:
        AgentAuditResponse: JSON con el job_id de tracking y el estado 'accepted'.

    Raises:
        HTTPException(400): Si la vista guardada no existe en el dataset.
        HTTPException(503): Si el dataset no está disponible.
        HTTPException(500): Si ocurre un error inesperado durante la validación.
    """
    # --- Obtener dataset activo de forma defensiva ---
    dataset: fo.Dataset = _get_dataset()

    # --- Generar job_id único para tracking ---
    job_id: str = str(uuid.uuid4())

    logger.info(
        f"[JOB {job_id}] POST /agent/audit · RECEIVED · "
        f"view='{request_body.saved_view_name}' · "
        f"provider='{request_body.vlm_provider}' · "
        f"threshold={request_body.confidence_threshold}"
    )

    try:
        # -------------------------------------------------------------------
        # VALIDACIÓN: Verificar que la vista guardada existe en el dataset.
        # Esta validación es crítica antes de encolar el job en background,
        # ya que el error de vista no encontrada debe ser reportado al cliente
        # de forma síncrona (HTTP 400), no de forma silenciosa en background.
        # -------------------------------------------------------------------
        available_views: list[str] = dataset.list_saved_views()

        if request_body.saved_view_name not in available_views:
            logger.warning(
                f"[JOB {job_id}] REJECTED · "
                f"Vista guardada '{request_body.saved_view_name}' no encontrada. "
                f"Vistas disponibles: {available_views}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"La vista guardada '{request_body.saved_view_name}' no existe "
                    f"en el dataset '{DATASET_NAME}'. "
                    f"Vistas disponibles: {available_views}. "
                    f"Consulta GET /api/v1/dataset/summary para ver todas las vistas disponibles, "
                    f"o crea la vista en FiftyOne antes de lanzar la auditoría."
                ),
            )

        # -------------------------------------------------------------------
        # CARGA DE LA VISTA GUARDADA
        # fo.Dataset.load_saved_view() retorna un fo.DatasetView que
        # representa el subconjunto filtrado del dataset según los criterios
        # con los que fue creada la vista en el Módulo 02 o Módulo 03.
        # -------------------------------------------------------------------
        logger.info(
            f"[JOB {job_id}] Cargando vista guardada '{request_body.saved_view_name}'..."
        )
        view: fo.DatasetView = dataset.load_saved_view(request_body.saved_view_name)
        view_sample_count: int = len(view)

        logger.info(
            f"[JOB {job_id}] Vista '{request_body.saved_view_name}' cargada. "
            f"Muestras en la vista: {view_sample_count}."
        )

        if view_sample_count == 0:
            logger.warning(
                f"[JOB {job_id}] La vista '{request_body.saved_view_name}' está vacía "
                f"(0 muestras). El pipeline VLM se ejecutará pero no procesará ninguna muestra."
            )

        # -------------------------------------------------------------------
        # ENCOLAR EL JOB EN BACKGROUND
        # BackgroundTasks.add_task() registra la función async y sus argumentos.
        # La función se ejecutará DESPUÉS de que esta función retorne la respuesta HTTP 202.
        # FastAPI garantiza que el background task NO bloquea la respuesta al cliente.
        # -------------------------------------------------------------------
        background_tasks.add_task(
            _execute_vlm_audit_in_background,
            view=view,
            provider=request_body.vlm_provider,
            confidence_threshold=request_body.confidence_threshold,
            job_id=job_id,
        )

        accepted_at: str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        response = AgentAuditResponse(
            status="accepted",
            job_id=job_id,
            message=(
                f"Job de auditoría VLM '{job_id}' aceptado y encolado en background. "
                f"Procesando {view_sample_count} muestras de la vista "
                f"'{request_body.saved_view_name}' con el proveedor "
                f"'{request_body.vlm_provider}' y umbral de confianza "
                f"{request_body.confidence_threshold}."
            ),
            saved_view_name=request_body.saved_view_name,
            vlm_provider=request_body.vlm_provider,
            confidence_threshold=request_body.confidence_threshold,
            accepted_at=accepted_at,
            tracking_hint=(
                "El procesamiento VLM ocurre de forma asíncrona en background. "
                "Consulta GET /api/v1/dataset/summary para verificar el estado "
                "del dataset una vez que el pipeline haya completado. "
                f"Usa el job_id '{job_id}' para correlacionar entradas en los logs del servidor."
            ),
        )

        logger.info(
            f"[JOB {job_id}] ACCEPTED · HTTP 202 enviado al cliente. "
            f"Background task encolado."
        )
        return response

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"[JOB {job_id}] ERROR INESPERADO durante validación: "
            f"{type(exc).__name__}: {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Error interno al procesar la solicitud de auditoría (job_id: {job_id}). "
                f"Tipo de error: {type(exc).__name__}. "
                f"Revisa los logs del servidor para el stack trace completo."
            ),
        )


# ============================================================================
# ENDPOINT DE HEALTH CHECK
# ============================================================================

@app.get(
    path="/health",
    summary="Health check del servidor API",
    description=(
        "Endpoint de verificación de salud del servidor. "
        "Retorna el estado del dataset FiftyOne y la conectividad con MongoDB. "
        "Útil para monitoreo automatizado, probes de Kubernetes y scripts de CI/CD."
    ),
    tags=["Infraestructura"],
)
async def health_check() -> dict[str, Any]:
    """
    Health check endpoint para monitoreo de infraestructura.

    Retorna HTTP 200 si el servidor está listo para procesar requests,
    HTTP 503 si el dataset no está disponible.
    """
    dataset_ready: bool = app_state.get("dataset_ready", False)
    dataset: Optional[fo.Dataset] = app_state.get("dataset")

    if not dataset_ready or dataset is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servidor en estado no-listo. Dataset FiftyOne no disponible.",
        )

    return {
        "status": "healthy",
        "dataset_name": DATASET_NAME,
        "dataset_ready": dataset_ready,
        "total_samples": len(dataset),
        "server_time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ============================================================================
# PUNTO DE ENTRADA PARA EJECUCIÓN DIRECTA (sin uvicorn CLI)
# ============================================================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # False en ejecución directa; usar --reload en CLI para desarrollo
        log_level="info",
        access_log=True,
    )
```

### 3.2 Estructura de directorios del módulo API

```
hackathon-repo/
├── api/
│   ├── __init__.py          # Hace de api/ un paquete Python importable
│   └── main.py              # Script completo de este módulo (código anterior)
├── vlm/
│   ├── __init__.py
│   └── pipeline.py          # Módulo 04: run_vlm_audit_pipeline()
├── docs/
│   ├── 01_environment.md
│   ├── 02_core_queries.md
│   ├── 03_brain.md
│   ├── 04_vlm_pipeline.md
│   ├── 05_mcp_plugins.md
│   └── 06_production_api.md  # Este archivo
└── requirements.txt
```

### 3.3 Dependencias de instalación

```bash
# Instalar dependencias del Módulo 06
pip install \
    "fastapi>=0.109.0" \
    "uvicorn[standard]>=0.27.0" \
    "pydantic>=2.6.0" \
    "fiftyone>=0.23.0"

# Verificar versiones instaladas
python -c "import fastapi; print(f'FastAPI: {fastapi.__version__}')"
python -c "import uvicorn; print(f'Uvicorn: {uvicorn.__version__}')"
python -c "import pydantic; print(f'Pydantic: {pydantic.__version__}')"
python -c "import fiftyone; print(f'FiftyOne: {fiftyone.__version__}')"
```

---

## 4. Protocolo de Despliegue en Caliente y Pruebas con `curl`

### 4.1 Comando de arranque con Uvicorn (recarga en caliente)

El siguiente comando levanta el servidor ASGI con todas las características necesarias para un entorno de desarrollo durante la hackathon: recarga automática ante cambios de código, logging verbose, acceso desde cualquier interfaz de red del host.

```bash
# ─────────────────────────────────────────────────────────────────────────────
# COMANDO DE ARRANQUE DEL SERVIDOR API REST
# Ejecutar desde la raíz del repositorio de la hackathon.
#
# PARÁMETROS EXPLICADOS:
#   api.main:app         → módulo Python 'api.main', instancia 'app' de FastAPI
#   --host 0.0.0.0       → escucha en todas las interfaces (localhost + red local)
#   --port 8000          → puerto HTTP obligatorio según la spec del sistema
#   --reload             → recarga automática del servidor ante cambios en el código
#                          fuente. CRÍTICO para iteración rápida en hackathon.
#                          NOTA: --reload NO debe usarse en producción real.
#   --log-level info     → nivel de logging verbose para debugging durante el evento
#   --reload-dir api/    → limitar la vigilancia de cambios al directorio api/
#                          para evitar reloads innecesarios por cambios en docs/ o data/
# ─────────────────────────────────────────────────────────────────────────────
uvicorn api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info \
    --reload-dir api/
```

**Salida esperada en el terminal tras el arranque exitoso:**

```
INFO:     Will watch for changes in these directories: ['.../api/']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using WatchFiles
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
2026-06-19T14:30:00 · hackathon_api.lifecycle · INFO · ======================================================================
2026-06-19T14:30:00 · hackathon_api.lifecycle · INFO · STARTUP · API REST FiftyOne Visual Agent
2026-06-19T14:30:00 · hackathon_api.lifecycle · INFO ·           Dataset objetivo: 'hackathon-dataset'
2026-06-19T14:30:00 · hackathon_api.lifecycle · INFO ·           Puerto HTTP: 8000
2026-06-19T14:30:00 · hackathon_api.lifecycle · INFO · Verificando conectividad con MongoDB (localhost:27017)...
2026-06-19T14:30:00 · hackathon_api.lifecycle · INFO · MongoDB conectado. Datasets en base de datos: ['hackathon-dataset']
2026-06-19T14:30:01 · hackathon_api.lifecycle · INFO · Cargando dataset 'hackathon-dataset'...
2026-06-19T14:30:01 · hackathon_api.lifecycle · INFO · STARTUP OK · Dataset 'hackathon-dataset' listo. Muestras: 1247. Schema: ['id', 'filepath', 'tags', 'metadata', 'ground_truth', 'uniqueness', 'mistakenness', 'clip_sim', 'vlm_audit'].
INFO:     Application startup complete.
```

### 4.2 Documentación interactiva automática (Swagger UI)

FastAPI genera documentación interactiva automáticamente. Una vez arrancado el servidor, accede a:

```
http://localhost:8000/docs      → Swagger UI (interfaz interactiva para probar endpoints)
http://localhost:8000/redoc     → ReDoc (documentación de referencia estructurada)
http://localhost:8000/openapi.json → Schema OpenAPI 3.0 en JSON crudo
```

### 4.3 Pruebas con `curl`: Endpoint GET `/api/v1/dataset/summary`

```bash
# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Consulta analítica del estado del dataset
#
# PARÁMETROS curl EXPLICADOS:
#   -s               → modo silencioso (suprime barra de progreso)
#   -X GET           → método HTTP GET (explícito para claridad)
#   -H "Accept: ..." → cabecera de tipo de contenido esperado
#   | python3 -m json.tool → formatea la respuesta JSON con indentación
# ─────────────────────────────────────────────────────────────────────────────
curl -s \
    -X GET \
    -H "Accept: application/json" \
    "http://localhost:8000/api/v1/dataset/summary" \
    | python3 -m json.tool
```

**Respuesta JSON esperada (ejemplo con dataset completo del sistema):**

```json
{
    "dataset_name": "hackathon-dataset",
    "total_samples": 1247,
    "field_schema": {
        "id": "ObjectIdField",
        "filepath": "StringField",
        "tags": "ListField",
        "metadata": "EmbeddedDocumentField",
        "ground_truth": "EmbeddedDocumentField",
        "uniqueness": "FloatField",
        "mistakenness": "FloatField",
        "clip_sim": "VectorField",
        "clip_vis": "VectorField",
        "vlm_audit": "EmbeddedDocumentField"
    },
    "label_classes": {
        "ground_truth": [
            "bird",
            "cat",
            "dog",
            "horse",
            "person"
        ],
        "vlm_audit": [
            "correct",
            "incorrect",
            "uncertain"
        ]
    },
    "avg_uniqueness": 0.731245,
    "avg_mistakenness": 0.124873,
    "saved_views": [
        "audit_subset_50",
        "high_uniqueness",
        "high_mistakenness",
        "mistaken_labels",
        "vlm_unprocessed"
    ],
    "generated_at": "2026-06-19T14:32:01Z"
}
```

```bash
# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Verificar el código de respuesta HTTP explícitamente
#
# -o /dev/null     → descartar el body de la respuesta (solo queremos el código)
# -w "%{http_code}" → imprimir solo el código HTTP de respuesta
# ─────────────────────────────────────────────────────────────────────────────
curl -s \
    -o /dev/null \
    -w "HTTP Status: %{http_code}\n" \
    -X GET \
    "http://localhost:8000/api/v1/dataset/summary"

# Salida esperada:
# HTTP Status: 200
```

```bash
# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: Medir la latencia del endpoint de summary
#
# -w "%{time_total}" → tiempo total de la request en segundos
# ─────────────────────────────────────────────────────────────────────────────
curl -s \
    -o /dev/null \
    -w "Latencia total: %{time_total}s\n" \
    -X GET \
    "http://localhost:8000/api/v1/dataset/summary"

# Salida esperada (MongoDB local, dataset 1247 muestras):
# Latencia total: 0.087s
```

### 4.4 Pruebas con `curl`: Endpoint POST `/api/v1/agent/audit`

```bash
# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: Lanzar auditoría asíncrona con gpt-4o sobre vista 'high_uniqueness'
#
# PARÁMETROS curl EXPLICADOS:
#   -X POST                      → método HTTP POST
#   -H "Content-Type: ..."       → cabecera que indica que el body es JSON
#   -H "Accept: ..."             → cabecera que indica que esperamos JSON en respuesta
#   -d '{ ... }'                 → body JSON de la request
#   | python3 -m json.tool       → formateo JSON de la respuesta
# ─────────────────────────────────────────────────────────────────────────────
curl -s \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{
        "saved_view_name": "high_uniqueness",
        "vlm_provider": "gpt-4o",
        "confidence_threshold": 0.80
    }' \
    "http://localhost:8000/api/v1/agent/audit" \
    | python3 -m json.tool
```

**Respuesta JSON esperada (HTTP 202 Accepted, retornada en < 100ms):**

```json
{
    "status": "accepted",
    "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "message": "Job de auditoría VLM 'f47ac10b-58cc-4372-a567-0e02b2c3d479' aceptado y encolado en background. Procesando 312 muestras de la vista 'high_uniqueness' con el proveedor 'gpt-4o' y umbral de confianza 0.8.",
    "saved_view_name": "high_uniqueness",
    "vlm_provider": "gpt-4o",
    "confidence_threshold": 0.8,
    "accepted_at": "2026-06-19T14:33:15Z",
    "tracking_hint": "El procesamiento VLM ocurre de forma asíncrona en background. Consulta GET /api/v1/dataset/summary para verificar el estado del dataset una vez que el pipeline haya completado. Usa el job_id 'f47ac10b-58cc-4372-a567-0e02b2c3d479' para correlacionar entradas en los logs del servidor."
}
```

```bash
# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: Lanzar auditoría con claude-3-5-sonnet sobre vista 'mistaken_labels'
#         con umbral de confianza más conservador
# ─────────────────────────────────────────────────────────────────────────────
curl -s \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{
        "saved_view_name": "mistaken_labels",
        "vlm_provider": "claude-3-5-sonnet",
        "confidence_threshold": 0.90
    }' \
    "http://localhost:8000/api/v1/agent/audit" \
    | python3 -m json.tool
```

```bash
# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: Verificar el código HTTP 202 explícitamente
# ─────────────────────────────────────────────────────────────────────────────
curl -s \
    -o /dev/null \
    -w "HTTP Status: %{http_code}\n" \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{
        "saved_view_name": "high_uniqueness",
        "vlm_provider": "gpt-4o",
        "confidence_threshold": 0.75
    }' \
    "http://localhost:8000/api/v1/agent/audit"

# Salida esperada:
# HTTP Status: 202
```

```bash
# ─────────────────────────────────────────────────────────────────────────────
# TEST 7: Verificar manejo de error 400 con vista inexistente
# ─────────────────────────────────────────────────────────────────────────────
curl -s \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{
        "saved_view_name": "vista_que_no_existe",
        "vlm_provider": "gpt-4o",
        "confidence_threshold": 0.75
    }' \
    "http://localhost:8000/api/v1/agent/audit" \
    | python3 -m json.tool

# Respuesta esperada (HTTP 400 Bad Request):
# {
#     "detail": "La vista guardada 'vista_que_no_existe' no existe en el dataset 'hackathon-dataset'. Vistas disponibles: ['audit_subset_50', 'high_uniqueness', ...]. Consulta GET /api/v1/dataset/summary para ver todas las vistas disponibles, o crea la vista en FiftyOne antes de lanzar la auditoría."
# }
```

```bash
# ─────────────────────────────────────────────────────────────────────────────
# TEST 8: Verificar manejo de error 422 con proveedor VLM inválido
# ─────────────────────────────────────────────────────────────────────────────
curl -s \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{
        "saved_view_name": "high_uniqueness",
        "vlm_provider": "gemini-pro-vision",
        "confidence_threshold": 0.75
    }' \
    "http://localhost:8000/api/v1/agent/audit" \
    | python3 -m json.tool

# Respuesta esperada (HTTP 422 Unprocessable Entity — validación Pydantic):
# {
#     "detail": [
#         {
#             "type": "value_error",
#             "loc": ["body", "vlm_provider"],
#             "msg": "Value error, Proveedor VLM 'gemini-pro-vision' no soportado. Proveedores válidos: ['claude-3-5-sonnet', 'gpt-4o'].",
#             "input": "gemini-pro-vision",
#             "url": "https://errors.pydantic.dev/2.6/v/value_error"
#         }
#     ]
# }
```

```bash
# ─────────────────────────────────────────────────────────────────────────────
# TEST 9: Health check del servidor
# ─────────────────────────────────────────────────────────────────────────────
curl -s \
    -X GET \
    -H "Accept: application/json" \
    "http://localhost:8000/health" \
    | python3 -m json.tool

# Respuesta esperada (HTTP 200 OK):
# {
#     "status": "healthy",
#     "dataset_name": "hackathon-dataset",
#     "dataset_ready": true,
#     "total_samples": 1247,
#     "server_time_utc": "2026-06-19T14:35:22Z"
# }
```

```bash
# ─────────────────────────────────────────────────────────────────────────────
# TEST 10: Script de test de integración completo (secuencial)
# Útil para ejecutar antes de la demo con los jueces.
# ─────────────────────────────────────────────────────────────────────────────
#!/usr/bin/env bash
set -e

BASE_URL="http://localhost:8000"
echo "════════════════════════════════════════════════════"
echo "  INTEGRATION TEST SUITE — FiftyOne Visual Agent API"
echo "════════════════════════════════════════════════════"

echo ""
echo "TEST 1/3: Health Check..."
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/health")
[ "$HEALTH_STATUS" = "200" ] && echo "  ✅ PASS (HTTP $HEALTH_STATUS)" || echo "  ❌ FAIL (HTTP $HEALTH_STATUS)"

echo ""
echo "TEST 2/3: Dataset Summary..."
SUMMARY_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/dataset/summary")
[ "$SUMMARY_STATUS" = "200" ] && echo "  ✅ PASS (HTTP $SUMMARY_STATUS)" || echo "  ❌ FAIL (HTTP $SUMMARY_STATUS)"

echo ""
echo "TEST 3/3: Agent Audit (POST)..."
AUDIT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{"saved_view_name": "high_uniqueness", "vlm_provider": "gpt-4o", "confidence_threshold": 0.75}' \
    "${BASE_URL}/api/v1/agent/audit")
[ "$AUDIT_STATUS" = "202" ] && echo "  ✅ PASS (HTTP $AUDIT_STATUS)" || echo "  ❌ FAIL (HTTP $AUDIT_STATUS)"

echo ""
echo "════════════════════════════════════════════════════"
echo "  Swagger UI disponible en: ${BASE_URL}/docs"
echo "════════════════════════════════════════════════════"
```

---

## Resumen de Endpoints de la API

| Método | Path | Status Code | Descripción | Bloqueo |
|--------|------|-------------|-------------|---------|
| `GET` | `/health` | `200 / 503` | Health check del servidor y disponibilidad del dataset | Síncrono (< 10ms) |
| `GET` | `/api/v1/dataset/summary` | `200 / 503 / 500` | Estado analítico completo: muestras, schema, clases, métricas Brain | Síncrono (< 200ms) |
| `POST` | `/api/v1/agent/audit` | `202 / 400 / 422 / 503 / 500` | Lanzar auditoría VLM asíncrona sobre vista guardada | No bloqueante (< 100ms) |

---

## Mapa de puertos del sistema completo

| Puerto | Proceso | Responsabilidad |
|--------|---------|-----------------|
| `27017` | MongoDB 7.0 | Persistencia del dataset FiftyOne y todos sus metadatos |
| `5151` | FiftyOne App | UI interactiva para revisión y anotación humana del dataset |
| `5152` | MCP Server (Módulo 05) | Tool-use integrado para Claude Code y Cursor |
| `8000` | **FastAPI REST API (este módulo)** | **Exposición HTTP/JSON del estado analítico y gatillado del agente** |

---

## Navegación cruzada

← Módulo anterior: [docs/05_mcp_plugins.md](./05_mcp_plugins.md) — Operador UI nativo `VLM_Auditor_Operator` y servidor MCP en el puerto 5152.

↑ Inicio del repositorio: [README.md](../README.md) — Índice completo de todos los módulos del repositorio de preparación técnica.

---

_Documento generado para el repositorio Staff-Level Technical Readiness · Hackathon Data Agents & Visual Agents · Junio 19, 2026_
