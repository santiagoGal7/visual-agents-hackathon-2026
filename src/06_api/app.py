"""
app.py

Servidor FastAPI de nivel industrial para la API REST del visual agent.
Orquesta:
1. Ciclo de vida asíncrono (lifespan) con verificación de conectividad y carga del dataset en MongoDB.
2. Endpoint GET /api/v1/dataset/summary para consultar metadata del dataset y esquemas.
3. Endpoint POST /api/v1/agent/audit con BackgroundTasks para procesar imágenes con VLM de forma no bloqueante.
"""

from __future__ import annotations

import os
import uuid
import logging
import asyncio
import importlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

import fiftyone as fo
from fastapi import FastAPI, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de Logging de nivel de producción
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s · %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ"
)
logger = logging.getLogger("api_server")

# Constantes del dataset
DATASET_NAME_ENV_VAR = "FIFTYONE_DATASET_NAME"
DEFAULT_DATASET_NAME = "hackathon-dataset"

# Estado global mutable del servidor
app_state: Dict[str, Any] = {
    "dataset": None,
    "dataset_ready": False,
}

# Carga dinámica del conector VLM
try:
    vlm_connector = importlib.import_module("src.04_agents.vlm_connector")
except ImportError as err:
    logger.error(f"No se pudo importar 'src.04_agents.vlm_connector'. Error: {err}")
    # Creamos un mock/stub en caso de que falte en tiempo de ejecución
    vlm_connector = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestión asíncrona del ciclo de vida del servidor ASGI (Startup y Shutdown).
    Valida la conectividad a MongoDB y carga el dataset de FiftyOne de forma inicial.
    """
    logger.info("=" * 70)
    logger.info("STARTUP · Inicializando el Servidor API REST de FiftyOne")
    
    dataset_name = os.getenv(DATASET_NAME_ENV_VAR, DEFAULT_DATASET_NAME)
    logger.info(f"Dataset oficial configurado: '{dataset_name}'")

    try:
        # Validar la conectividad con MongoDB
        logger.info("Verificando conexión con la base de datos MongoDB (localhost:27017)...")
        available_datasets = fo.list_datasets()
        logger.info(f"MongoDB conectado exitosamente. Datasets disponibles: {available_datasets}")

        # Comprobar la existencia del dataset
        if dataset_name not in available_datasets:
            logger.critical(
                f"El dataset '{dataset_name}' no existe en MongoDB. "
                f"Ejecute el módulo de inicialización/ingesta antes de levantar el servidor."
            )
            # Fallar rápido al iniciar el proceso
            raise SystemExit(f"Error: Dataset '{dataset_name}' no encontrado.")

        # Carga inicial del dataset en el estado global
        logger.info(f"Cargando dataset '{dataset_name}'...")
        dataset = fo.load_dataset(dataset_name)

        # Forzar persistencia para evitar pérdidas de datos accidentales
        if not dataset.persistent:
            logger.warning("El dataset no estaba marcado como persistente. Corrigiendo a persistent=True...")
            dataset.persistent = True
            dataset.save()

        app_state["dataset"] = dataset
        app_state["dataset_ready"] = True
        logger.info(f"STARTUP OK · Dataset '{dataset_name}' cargado con {len(dataset)} samples.")
        logger.info("=" * 70)

    except SystemExit:
        raise
    except Exception as e:
        logger.critical(f"STARTUP FAILURE: Fallo irrecuperable al arrancar el servidor: {e}", exc_info=True)
        raise SystemExit(f"No se pudo iniciar el servidor API: {e}")

    yield

    # Shutdown
    logger.info("=" * 70)
    logger.info("SHUTDOWN · Limpiando recursos y desconectando el Servidor API")
    app_state["dataset_ready"] = False
    app_state["dataset"] = None
    logger.info("SHUTDOWN OK · Servidor detenido limpiamente.")
    logger.info("=" * 70)


# Inicialización de la app FastAPI
app = FastAPI(
    title="FiftyOne Visual Agent REST API",
    description="Servidor API REST de nivel industrial para el Visual Agent.",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class DatasetSummaryResponse(BaseModel):
    dataset_name: str = Field(..., description="Nombre del dataset oficial.")
    total_samples: int = Field(..., description="Conteo total de muestras del dataset.")
    field_schema: Dict[str, str] = Field(..., description="Mapeo de nombres de campos y sus tipos en FiftyOne.")
    saved_views: List[str] = Field(default_factory=list, description="Lista de vistas guardadas disponibles.")
    avg_uniqueness: Optional[float] = Field(None, description="Promedio de la métrica 'uniqueness' (si está calculada).")
    avg_mistakenness: Optional[float] = Field(None, description="Promedio de la métrica 'mistakenness' (si está calculada).")
    generated_at: str = Field(..., description="Timestamp de generación (UTC).")


class AuditRequest(BaseModel):
    saved_view_name: str = Field(..., min_length=1, description="Nombre de la vista guardada a auditar.")
    provider: str = Field(..., description="Proveedor VLM. Valores válidos: 'gpt-4o' o 'claude-3-5-sonnet'.")
    min_confidence: float = Field(0.75, ge=0.0, le=1.0, description="Umbral de confianza mínimo [0.0 - 1.0].")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        valid_providers = {"gpt-4o", "claude-3-5-sonnet"}
        if value not in valid_providers:
            raise ValueError(f"Proveedor '{value}' no es válido. Debe ser uno de: {sorted(valid_providers)}")
        return value


class AuditResponse(BaseModel):
    status: str = Field("accepted", description="Estado del Job.")
    job_id: str = Field(..., description="UUID identificador único del Job de background.")
    message: str = Field(..., description="Información detallada sobre el job aceptado.")
    saved_view_name: str = Field(..., description="Vista guardada seleccionada.")
    provider: str = Field(..., description="Proveedor del VLM.")
    min_confidence: float = Field(..., description="Umbral de confianza configurado.")
    accepted_at: str = Field(..., description="Timestamp de aceptación (UTC).")


# ============================================================================
# HELPERS
# ============================================================================

def _get_active_dataset() -> fo.Dataset:
    """
    Retorna el dataset activo desde el estado global de forma segura y defensiva.
    """
    if not app_state.get("dataset_ready") or app_state.get("dataset") is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio no está listo. El dataset FiftyOne se está inicializando o MongoDB está desconectado."
        )
    return app_state["dataset"]


async def _execute_vlm_audit_in_background(
    view: fo.DatasetView,
    provider: str,
    min_confidence: float,
    job_id: str
) -> None:
    """
    Pipeline asíncrono ejecutado en BackgroundTasks para auditar la vista guardada seleccionada.
    """
    logger.info(f"[JOB {job_id}] BACKGROUND START · Procesando vista con VLM {provider}. Muestras: {len(view)}.")
    
    if vlm_connector is None:
        logger.error(f"[JOB {job_id}] BACKGROUND FAILURE · El módulo 'vlm_connector' no está disponible.")
        return

    # Usar un semáforo para no saturar los rate limits de los proveedores
    concurrency_semaphore = asyncio.Semaphore(5)

    async def audit_sample(sample: fo.Sample) -> None:
        async with concurrency_semaphore:
            try:
                # 1. Percepción: Codificar la imagen local
                base64_image, media_type = vlm_connector.encode_image_to_base64(sample.filepath)

                # 2. Razonamiento: Llamar al VLM correspondiente
                # Mapear 'claude-3-5-sonnet' al identificador del modelo correcto
                vlm_model = "gpt-4o" if provider == "gpt-4o" else "claude-3-5-sonnet-20241022"
                
                if provider == "gpt-4o":
                    raw_response = await vlm_connector.query_gpt4o_vision(
                        api_key=None,
                        base64_image=base64_image,
                        prompt=vlm_connector.SYSTEM_PROMPT_VISION_ANALYST,
                        model=vlm_model,
                        media_type=media_type
                    )
                else:
                    raw_response = await vlm_connector.query_claude_vision(
                        api_key=None,
                        base64_image=base64_image,
                        prompt=vlm_connector.SYSTEM_PROMPT_VISION_ANALYST,
                        model=vlm_model,
                        media_type=media_type
                    )

                # 3. Postprocesamiento defensivo del JSON retornado
                vlm_data = vlm_connector.parse_vlm_response(raw_response)

                # 4. Acción: Guardar los resultados en FiftyOne
                # a) Inyectar tags sugeridos (sin duplicar)
                existing_tags = set(sample.tags or [])
                new_tags = [t for t in vlm_data.get("suggested_tags", []) if t not in existing_tags]
                sample.tags.extend(new_tags)

                # b) Determinar el veredicto del VLM usando el umbral min_confidence
                confidence = float(vlm_data.get("confidence", 0.0))
                if confidence < min_confidence:
                    label = "uncertain"
                else:
                    label = "potential_mistake" if vlm_data.get("potential_mistake", False) else "verified"

                sample["vlm_audit"] = fo.Classification(
                    label=label,
                    confidence=confidence
                )
                sample["vlm_rationale"] = vlm_data.get("rationale", "")

                # Guardar el sample de forma persistente
                sample.save()
                logger.info(f"[JOB {job_id}] Sample {sample.id} auditado. Label: {label}, Conf: {confidence:.2f}")

            except Exception as e:
                logger.error(f"[JOB {job_id}] Error procesando sample {sample.id}: {e}", exc_info=True)

    try:
        tasks = [audit_sample(sample) for sample in view]
        await asyncio.gather(*tasks)
        
        # Guardar cambios a nivel del dataset principal
        dataset = _get_active_dataset()
        dataset.save()
        logger.info(f"[JOB {job_id}] BACKGROUND COMPLETE · Vista guardada completamente auditada.")
    except Exception as e:
        logger.error(f"[JOB {job_id}] BACKGROUND FAILURE · Fallo en la ejecución del pipeline VLM: {e}", exc_info=True)


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get(
    "/api/v1/dataset/summary",
    response_model=DatasetSummaryResponse,
    status_code=status.HTTP_200_OK,
    tags=["Dataset"]
)
async def get_dataset_summary() -> DatasetSummaryResponse:
    """
    Retorna información general del dataset FiftyOne cargado:
    conteo total, esquema de campos y métricas analíticas.
    """
    dataset = _get_active_dataset()

    try:
        # Obtener esquema de campos
        raw_schema = dataset.get_field_schema()
        field_schema = {name: type(field).__name__ for name, field in raw_schema.items()}

        # Calcular promedios para métricas de Brain (Módulo 03) si existen
        avg_uniqueness = None
        if "uniqueness" in field_schema:
            try:
                avg_uniqueness = dataset.mean("uniqueness")
            except Exception:
                pass

        avg_mistakenness = None
        if "mistakenness" in field_schema:
            try:
                avg_mistakenness = dataset.mean("mistakenness")
            except Exception:
                pass

        return DatasetSummaryResponse(
            dataset_name=dataset.name,
            total_samples=len(dataset),
            field_schema=field_schema,
            saved_views=dataset.list_saved_views(),
            avg_uniqueness=avg_uniqueness,
            avg_mistakenness=avg_mistakenness,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    except Exception as e:
        logger.error(f"Error al computar el resumen del dataset: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar el resumen del dataset FiftyOne: {e}"
        )


@app.post(
    "/api/v1/agent/audit",
    response_model=AuditResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Agent"]
)
async def post_agent_audit(
    request: AuditRequest,
    background_tasks: BackgroundTasks
) -> AuditResponse:
    """
    Lanza una auditoría multimodal asíncrona sobre una vista guardada específica.
    """
    dataset = _get_active_dataset()
    job_id = str(uuid.uuid4())

    # Validar de forma síncrona si la vista guardada existe
    saved_views = dataset.list_saved_views()
    if request.saved_view_name not in saved_views:
        logger.warning(f"La vista guardada '{request.saved_view_name}' no existe. Vistas: {saved_views}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La vista '{request.saved_view_name}' no existe en el dataset. Vistas disponibles: {saved_views}"
        )

    # Cargar la vista guardada
    try:
        view = dataset.load_saved_view(request.saved_view_name)
    except Exception as e:
        logger.error(f"Error cargando la vista '{request.saved_view_name}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al cargar la vista guardada: {e}"
        )

    # Encolar el procesamiento en background para no bloquear la respuesta HTTP
    background_tasks.add_task(
        _execute_vlm_audit_in_background,
        view=view,
        provider=request.provider,
        min_confidence=request.min_confidence,
        job_id=job_id
    )

    accepted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    message = (
        f"Job '{job_id}' de auditoría asíncrona aceptado. Procesando {len(view)} samples "
        f"de la vista '{request.saved_view_name}' usando {request.provider}."
    )

    return AuditResponse(
        status="accepted",
        job_id=job_id,
        message=message,
        saved_view_name=request.saved_view_name,
        provider=request.provider,
        min_confidence=request.min_confidence,
        accepted_at=accepted_at
    )


@app.get("/health", status_code=status.HTTP_200_OK, tags=["System"])
async def health_check() -> Dict[str, Any]:
    """
    Health check para verificar el estado del servidor y la base de datos MongoDB.
    """
    is_ready = app_state.get("dataset_ready", False)
    dataset = app_state.get("dataset")
    
    if not is_ready or dataset is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servidor no saludable: El dataset FiftyOne no está listo o la base de datos no está activa."
        )

    return {
        "status": "healthy",
        "dataset_name": dataset.name,
        "dataset_ready": is_ready,
        "total_samples": len(dataset),
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
