"""
vlm_connector.py

Módulo de conexión con Vision-Language Models (VLMs) para auditoría multimodal.
Implementa:
1. Carga de variables de entorno mediante python-dotenv.
2. Codificación defensiva de imágenes a Base64 con verificación de integridad usando Pillow.
3. Consultas asíncronas a GPT-4o (OpenAI SDK >= 1.0.0) y Claude (Anthropic SDK >= 0.20.0).
4. Parseo y validación de esquemas JSON estructurados requeridos para el pipeline.
"""

import os
import base64
import json
import logging
import asyncio
from pathlib import Path
from typing import Tuple, Dict, Any, List, Optional
from PIL import Image, UnidentifiedImageError
from dotenv import load_dotenv

# Importaciones de SDKs oficiales
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

# Configuración básica de logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("vlm_connector")

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# System Prompt Maestro para obligar al VLM a retornar JSON estricto
SYSTEM_PROMPT_VISION_ANALYST = """
Eres un Auditor Senior de Visión Artificial integrado en un pipeline de FiftyOne. 
Tu única función es analizar la imagen proporcionada y devolver una evaluación técnica, objetiva y estructurada. 
No eres un asistente conversacional: no saludes, no expliques tu razonamiento en prosa, no agregues comentarios fuera del esquema solicitado.

REGLAS ESTRICTAS:
1. Responde EXCLUSIVAMENTE con un objeto JSON válido. No incluyes texto explicativo antes o después del JSON. No envuelvas la respuesta en bloques de markdown (no uses comillas triples de ningún tipo).
2. No inventes información que no sea visualmente verificable en la imagen. Si no puedes determinar un campo con certeza razonable, indícalo explícitamente en "rationale" en lugar de alucinar contenido.
3. Si la imagen está corrupta, borrosa, o no es analizable, indícalo en el campo "potential_mistake" como true y explica por qué en "rationale".
4. El campo "confidence" debe reflejar tu certeza real sobre la etiqueta asignada, no un valor arbitrario cercano a 1.0 por defecto. Debe ser un float entre 0.0 y 1.0.
5. El campo "potential_mistake" debe ser true si sospechas que una etiqueta o anotación previa del dataset podría ser incorrecta a la luz de lo que observas en la imagen.

Responde ÚNICAMENTE con un objeto JSON que siga EXACTAMENTE este esquema, sin campos adicionales y sin omitir ninguno de los listados:

{
  "suggested_tags": ["string", "..."],
  "confidence": 0.0,
  "potential_mistake": false,
  "rationale": "string"
}
""".strip()

# Mapeo de extensiones de archivo a MIME types soportados por los VLMs
_MIME_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}


def encode_image_to_base64(filepath: str) -> Tuple[str, str]:
    """
    Codifica una imagen local a una cadena Base64 junto con su MIME type inferido.
    Utiliza Pillow para verificar la integridad del archivo antes de realizar
    la codificación para evitar llamadas costosas a la API con archivos corruptos.

    Args:
        filepath: Ruta al archivo de imagen en disco.

    Returns:
        Una tupla (base64_string, media_type), ej. ("iVBORw0KG...", "image/png").

    Raises:
        FileNotFoundError: Si el archivo no existe.
        ValueError: Si el archivo existe pero no es una imagen válida o legible.
    """
    path = Path(filepath)

    if not path.exists():
        logger.error(f"Archivo no encontrado en: {filepath}")
        raise FileNotFoundError(f"No se encontró la imagen en: {filepath}")

    extension = path.suffix.lstrip(".").lower()
    media_type = _MIME_TYPES.get(extension, "image/jpeg")

    # Validación defensiva con Pillow
    try:
        with Image.open(path) as img:
            img.verify()  # Validación rápida sin cargar la imagen completa en memoria
    except (UnidentifiedImageError, OSError) as e:
        logger.error(f"La validación de la imagen falló para: {filepath}. Error: {e}")
        raise ValueError(f"El archivo no es una imagen válida: {filepath}") from e

    # Codificación de la imagen a base64
    try:
        with open(path, "rb") as image_file:
            raw_bytes = image_file.read()
        encoded_string = base64.b64encode(raw_bytes).decode("utf-8")
        return encoded_string, media_type
    except Exception as e:
        logger.error(f"Error al leer y codificar el archivo {filepath}: {e}")
        raise OSError(f"No se pudo leer el archivo de imagen: {filepath}") from e


async def query_gpt4o_vision(
    api_key: Optional[str],
    base64_image: str,
    prompt: str,
    model: str = "gpt-4o",
    media_type: str = "image/jpeg"
) -> str:
    """
    Envía una imagen codificada en Base64 junto con un prompt de texto a GPT-4o
    usando el SDK oficial y asíncrono de OpenAI.

    Args:
        api_key: API key de OpenAI. Si es None o vacía, se resuelve del entorno (OPENAI_API_KEY).
        base64_image: Imagen codificada en Base64 sin prefijos de data URI.
        prompt: Instrucción de texto para el modelo.
        model: Identificador del modelo (por defecto 'gpt-4o').
        media_type: El tipo MIME de la imagen (por defecto 'image/jpeg').

    Returns:
        String con el contenido devuelto por el modelo (esperado JSON).
    """
    resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_api_key:
        raise ValueError(
            "API Key de OpenAI no configurada. Pásala como argumento o define OPENAI_API_KEY en el entorno."
        )

    # Crear cliente de OpenAI asíncrono
    client = AsyncOpenAI(api_key=resolved_api_key)

    try:
        logger.info(f"Enviando solicitud VLM a OpenAI ({model})...")
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            max_tokens=1000,
            temperature=0.0,  # Determinismo para auditorías
            response_format={"type": "json_object"},  # Enforzar formato JSON a nivel API
        )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("OpenAI devolvió una respuesta nula.")
        return content.strip()

    except Exception as e:
        logger.error(f"Fallo al consultar GPT-4o Vision: {e}")
        raise


async def query_claude_vision(
    api_key: Optional[str],
    base64_image: str,
    prompt: str,
    model: str = "claude-3-5-sonnet-20241022",
    media_type: str = "image/jpeg"
) -> str:
    """
    Envía una imagen codificada en Base64 junto con un prompt de texto a Claude
    usando el SDK oficial y asíncrono de Anthropic.

    Args:
        api_key: API key de Anthropic. Si es None o vacía, se resuelve del entorno (ANTHROPIC_API_KEY).
        base64_image: Imagen codificada en Base64 sin prefijos de data URI.
        prompt: Instrucción de texto para el modelo.
        model: Identificador del modelo (por defecto 'claude-3-5-sonnet-20241022').
        media_type: El tipo MIME de la imagen (por defecto 'image/jpeg').

    Returns:
        String con el contenido de texto devuelto por el modelo (esperado JSON).
    """
    resolved_api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not resolved_api_key:
        raise ValueError(
            "API Key de Anthropic no configurada. Pásala como argumento o define ANTHROPIC_API_KEY en el entorno."
        )

    # Crear cliente de Anthropic asíncrono
    client = AsyncAnthropic(api_key=resolved_api_key)

    try:
        logger.info(f"Enviando solicitud VLM a Anthropic ({model})...")
        response = await client.messages.create(
            model=model,
            max_tokens=1000,
            temperature=0.0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_image,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        content = response.content[0].text
        if not content:
            raise ValueError("Anthropic devolvió una respuesta vacía.")
        return content.strip()

    except Exception as e:
        logger.error(f"Fallo al consultar Claude Vision: {e}")
        raise


def parse_vlm_response(raw_response: str) -> Dict[str, Any]:
    """
    Limpia y parsea de forma defensiva la respuesta de texto del VLM a un diccionario de Python.
    Maneja automáticamente envoltorios de bloques de código markdown (```json ... ```)
    y verifica que se cumpla el esquema requerido con valores por defecto seguros.

    Args:
        raw_response: La cadena de respuesta cruda del modelo.

    Returns:
        Diccionario validado con llaves: suggested_tags, confidence, potential_mistake y rationale.

    Raises:
        json.JSONDecodeError: Si el string no puede ser parseado como JSON válido.
    """
    cleaned = raw_response.strip()

    # Sanitizar bloques de código markdown si el modelo los incluyó
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[len("json"):].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Fallo al decodificar JSON del VLM: {e}")
        logger.error(f"Respuesta cruda recibida: {raw_response!r}")
        raise

    # Esquema y valores predeterminados para garantizar robustez
    schema_defaults = {
        "suggested_tags": [],
        "confidence": 0.0,
        "potential_mistake": False,
        "rationale": "",
    }

    # Validar tipos e inyectar valores por defecto si faltan campos
    validated_data = {}
    
    # suggested_tags (debe ser list)
    suggested_tags = data.get("suggested_tags")
    if isinstance(suggested_tags, list):
        validated_data["suggested_tags"] = [str(item) for item in suggested_tags]
    else:
        logger.warning(f"suggested_tags inválido o ausente en el JSON. Usando por defecto: {schema_defaults['suggested_tags']}")
        validated_data["suggested_tags"] = schema_defaults["suggested_tags"]

    # confidence (debe ser float)
    confidence = data.get("confidence")
    try:
        validated_data["confidence"] = float(confidence) if confidence is not None else schema_defaults["confidence"]
    except (ValueError, TypeError):
        logger.warning(f"confidence inválido en el JSON. Usando por defecto: {schema_defaults['confidence']}")
        validated_data["confidence"] = schema_defaults["confidence"]

    # potential_mistake (debe ser bool)
    potential_mistake = data.get("potential_mistake")
    if isinstance(potential_mistake, bool):
        validated_data["potential_mistake"] = potential_mistake
    else:
        # Intentar convertir en caso de que venga como string/número
        if str(potential_mistake).lower() in ("true", "1", "yes"):
            validated_data["potential_mistake"] = True
        else:
            validated_data["potential_mistake"] = False

    # rationale (debe ser string)
    rationale = data.get("rationale")
    validated_data["rationale"] = str(rationale) if rationale is not None else schema_defaults["rationale"]

    return validated_data


async def process_view_with_vlm(view: Any, provider: str, min_confidence: float, concurrency: int = 5) -> None:
    """
    Procesa una vista (DatasetView) de FiftyOne de forma asíncrona utilizando el VLM seleccionado.
    Inyecta los resultados del VLM en cada una de las muestras.
    """
    import fiftyone as fo
    
    concurrency_semaphore = asyncio.Semaphore(concurrency)

    async def audit_sample(sample: Any) -> None:
        async with concurrency_semaphore:
            try:
                # 1. Percepción: Codificar la imagen local
                base64_image, media_type = encode_image_to_base64(sample.filepath)

                # 2. Razonamiento: Llamar al VLM correspondiente
                vlm_model = "gpt-4o" if provider == "gpt-4o" else "claude-3-5-sonnet-20241022"
                
                if provider == "gpt-4o":
                    raw_response = await query_gpt4o_vision(
                        api_key=None,
                        base64_image=base64_image,
                        prompt=SYSTEM_PROMPT_VISION_ANALYST,
                        model=vlm_model,
                        media_type=media_type
                    )
                else:
                    raw_response = await query_claude_vision(
                        api_key=None,
                        base64_image=base64_image,
                        prompt=SYSTEM_PROMPT_VISION_ANALYST,
                        model=vlm_model,
                        media_type=media_type
                    )

                # 3. Postprocesamiento defensivo del JSON retornado
                vlm_data = parse_vlm_response(raw_response)

                # 4. Acción: Guardar los resultados en FiftyOne
                # a) Inyectar tags sugeridos
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

                sample.save()
                logger.info(f"Sample {sample.id} auditado. Label: {label}, Conf: {confidence:.2f}")

            except Exception as e:
                logger.error(f"Error procesando sample {sample.id}: {e}", exc_info=True)

    tasks = [audit_sample(sample) for sample in view]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    print("=== VLM Connector Module ===")
    print("Este módulo contiene clientes asíncronos para VLM (OpenAI / Anthropic).")
    print(f"OPENAI_API_KEY configurada: {'Sí' if os.getenv('OPENAI_API_KEY') else 'No'}")
    print(f"ANTHROPIC_API_KEY configurada: {'Sí' if os.getenv('ANTHROPIC_API_KEY') else 'No'}")
