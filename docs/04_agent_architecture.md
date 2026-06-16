# 🤖 docs/04_agent_architecture.md — Arquitectura de Razonamiento Multimodal

## Hackathon Data Agents & Visual Agents | Voxel51

---

## Introducción

Este documento define la **arquitectura cognitiva** del agente visual: cómo percibe imágenes, cómo razona sobre ellas usando un VLM (*Vision Language Model*), y cómo traduce ese razonamiento en estructuras de datos que el SDK de FiftyOne puede consumir directamente. Es el puente entre la curación de datos ([`docs/03_brain_curation.md`](./03_brain_curation.md)) y la capa de Operators/Skills ([`docs/05_agent_operators.md`](./05_agent_operators.md)).

Regresar a: [`README.md`](../README.md) | Anterior: [`03_brain_curation.md`](./03_brain_curation.md)

---

## 1. La Anatomía del Razonamiento en un Agente Visual

### 1.1 El Ciclo de Vida: Percepción → Razonamiento → Acción

Todo agente visual funcional, sin importar su complejidad, se reduce a tres fases secuenciales. Diseñar el sistema explícitamente alrededor de estas fases evita arquitecturas ambiguas donde el "razonamiento" y la "acción" quedan mezclados en una sola función monolítica, difícil de depurar bajo presión de tiempo durante la hackathon.

La razón de fondo es de **responsabilidad única**: cada fase tiene una entrada y una salida bien definidas, lo que permite testear, mockear y sustituir cualquiera de ellas sin tocar las demás. Esto es crítico cuando el equipo necesita cambiar de proveedor de VLM a mitad de la competencia, o cuando un juez pide ver "qué pasó exactamente" en un caso de error.

| Fase | Descripción | Entrada | Salida |
|------|-------------|---------|--------|
| **1. Percepción** | El agente recibe la referencia visual: un `Sample` de FiftyOne, su `filepath`, y opcionalmente metadata ya existente (labels previos, embeddings, scores del Brain). En esta fase se decide *cómo* se va a transportar la imagen hacia el modelo. | `fo.Sample`, ruta de imagen o frame de video | Payload codificado (Base64 o URL accesible) listo para transmisión al VLM |
| **2. Razonamiento** | El VLM (GPT-4o, Claude) procesa la imagen junto con un *prompt* del sistema o del usuario, generando una interpretación semántica del contenido visual. Esta es la única fase que depende del proveedor externo. | Imagen codificada + prompt + contexto del dataset | Respuesta del modelo, idealmente JSON estructurado |
| **3. Acción** | El resultado del razonamiento se traduce en una operación concreta sobre FiftyOne: inyectar un `fo.Classification`, poblar tags, marcar una bandera de calidad, o disparar un `Operator` de la capa superior. | JSON estructurado del VLM | Mutación controlada del `Sample` o construcción de una `View` |

> 🧩 **Principio de diseño:** Cada fase debe vivir en su propia función, testeable de forma aislada. Si el VLM cambia de proveedor (OpenAI → Anthropic) a mitad de la hackathon, solo la fase de **Razonamiento** debe modificarse — Percepción y Acción permanecen intactas. Esto no es un capricho académico: es lo que permite a un equipo de cuatro personas trabajar en paralelo sin pisarse el código.

El flujo conceptual completo es el siguiente:

```
[Sample FiftyOne]
        │
        ▼
┌──────────────┐      ┌────────────────┐      ┌─────────────────────┐
│  PERCEPCIÓN  │ ───▶ │  RAZONAMIENTO  │ ───▶ │       ACCIÓN        │
│ (encode img) │      │  (VLM + JSON)  │      │ (fo.Classification / │
│              │      │                 │      │  tags / metadata)   │
└──────────────┘      └────────────────┘      └─────────────────────┘
```

### 1.2 Desacoplamiento de Carga Útil (Payload)

Una decisión arquitectónica que parece trivial pero que determina la latencia, el costo y la estabilidad de todo el agente es **qué viaja realmente hacia el LLM**.

Las imágenes, especialmente en datasets de visión computacional, pueden pesar varios megabytes cada una. Si el agente intentara enviar el objeto `Sample` completo —con todos sus campos, labels anidados, embeddings de alta dimensionalidad y metadata de FiftyOne— al LLM en cada llamada, ocurrirían tres problemas simultáneos:

1. **Explosión de tokens y costo.** Los modelos de lenguaje no "ven" bytes binarios crudos de forma eficiente; cualquier dato no esencial que se cuele en el prompt (metadata de Mongo, IDs internos, embeddings de cientos de dimensiones) infla el conteo de tokens sin aportar señal útil al razonamiento visual.
2. **Acoplamiento estructural innecesario.** El VLM no necesita saber qué es un `DatasetView` o cómo está indexado un campo en MongoDB; solo necesita la imagen y una instrucción. Mezclar la representación interna de FiftyOne con el contrato de la API del proveedor crea una dependencia frágil: cualquier cambio en el esquema interno de FiftyOne podría romper silenciosamente las llamadas al modelo.
3. **Riesgo de fuga de datos sensibles.** Enviar el objeto completo del `Sample` puede filtrar campos que no deberían salir del entorno controlado (rutas absolutas del sistema de archivos, IDs de proyectos internos, anotaciones de otros pipelines).

La solución es **desacoplar el payload**: la fase de Percepción extrae *únicamente* lo que el VLM necesita —los bytes de la imagen codificados en Base64, o una URL pública/firmada si el proveedor soporta referencias remotas— y descarta todo lo demás antes de construir la llamada a la API. El `Sample` de FiftyOne nunca cruza la frontera de red; solo lo hace su representación visual mínima. Esto mantiene el contrato entre Percepción y Razonamiento limpio, predecible, y barato en tokens.

---

## 2. Configuración e Inferencia Multimodal con VLMs (Código Limpio)

Esta sección entrega tres funciones independientes y listas para producción: una utilidad de codificación de imágenes reutilizable por ambos proveedores, y dos funciones de inferencia —una para GPT-4o vía el SDK moderno de OpenAI (`openai>=1.0.0`), y otra para Claude vía el SDK moderno de Anthropic (`anthropic>=0.20.0`).

### 2.1 Función Auxiliar de Codificación: `encode_image_to_base64`

Esta función vive en un módulo compartido (`vlm_utils.py`) porque ambos proveedores —OpenAI y Anthropic— requieren la imagen codificada en Base64, junto con su `media_type` (MIME type) correctamente inferido a partir de la extensión del archivo. Centralizarla evita duplicar lógica de codificación en cada cliente.

```python
"""
vlm_utils.py
Utilidades compartidas de codificación de imágenes para clientes VLM.
Usa la librería estándar `base64` más Pillow como validación defensiva
de que el archivo es efectivamente una imagen legible antes de gastar
una llamada de API en un archivo corrupto.
"""

import base64
from pathlib import Path

from PIL import Image, UnidentifiedImageError

# Mapeo de extensiones de archivo a MIME types soportados por los VLMs.
# Mantenerlo explícito (en vez de adivinar con mimetypes.guess_type)
# evita sorpresas con extensiones poco comunes o mal formadas.
_MIME_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}


def encode_image_to_base64(filepath: str) -> tuple[str, str]:
    """
    Codifica una imagen local (típicamente sample.filepath de FiftyOne)
    a una cadena Base64, junto con su MIME type inferido.

    Por qué validar con Pillow antes de codificar: si el archivo está
    corrupto o truncado, preferimos fallar aquí —de forma rápida y barata—
    en lugar de descubrirlo después de haber gastado una llamada de API
    completa al VLM con un payload inválido.

    Args:
        filepath: Ruta absoluta al archivo de imagen en disco.

    Returns:
        Una tupla (base64_string, media_type), ej. ("iVBORw0KG...", "image/png").

    Raises:
        FileNotFoundError: si la ruta no existe.
        ValueError: si el archivo existe pero no es una imagen legible.
    """
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(f"No se encontró la imagen en: {filepath}")

    extension = path.suffix.lstrip(".").lower()
    media_type = _MIME_TYPES.get(extension, "image/jpeg")

    try:
        with Image.open(path) as img:
            img.verify()  # Validación rápida de integridad, sin decodificar todo el buffer
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError(f"El archivo no es una imagen válida: {filepath}") from e

    with open(path, "rb") as image_file:
        raw_bytes = image_file.read()

    encoded = base64.b64encode(raw_bytes).decode("utf-8")
    return encoded, media_type
```

### 2.2 Inferencia con GPT-4o: `query_gpt4o_vision`

Esta función usa el SDK moderno de OpenAI (`openai>=1.0.0`), basado en clientes orientados a objetos (`AsyncOpenAI`) en lugar de las funciones de módulo del SDK legacy (`openai.ChatCompletion.create`, ya deprecado). Se fuerza `response_format={"type": "json_object"}` para activar el *JSON Mode* nativo del proveedor, lo cual reduce —aunque no elimina del todo— la necesidad de parsing defensivo en la fase de Acción.

```python
"""
vlm_openai_client.py
Cliente para inferencia multimodal con GPT-4o usando el SDK >=1.0.0 de OpenAI.
Requiere: pip install "openai>=1.0.0"
"""

import asyncio

from openai import AsyncOpenAI

from vlm_utils import encode_image_to_base64

# El cliente toma la API key automáticamente desde la variable de entorno
# OPENAI_API_KEY (ver docs/01_env_setup.md, Sección 4). No hardcodear la key.
client = AsyncOpenAI()


async def query_gpt4o_vision(api_key: str, base64_image: str, prompt: str) -> str:
    """
    Envía una imagen ya codificada en Base64 junto con un prompt de texto
    a GPT-4o y retorna la respuesta cruda del modelo como string.

    Por qué recibir base64_image como parámetro (y no el filepath): esta
    función pertenece exclusivamente a la fase de Razonamiento. La
    codificación de la imagen es responsabilidad de la fase de Percepción
    (encode_image_to_base64), y mantener esa frontera explícita es lo que
    permite sustituir el proveedor sin tocar el resto del pipeline.

    Args:
        api_key: API key de OpenAI. Se acepta explícitamente por claridad
            de contrato, aunque el cliente por defecto ya la resuelve desde
            la variable de entorno OPENAI_API_KEY.
        base64_image: Imagen codificada en Base64 (sin el prefijo data URI).
        prompt: Instrucción de texto (system prompt o prompt de usuario)
            que acompaña a la imagen.

    Returns:
        El contenido de texto crudo devuelto por el modelo (string JSON
        si se respetó el JSON Mode, pero debe tratarse como no confiable
        hasta ser parseado defensivamente).
    """
    scoped_client = AsyncOpenAI(api_key=api_key) if api_key else client

    response = await scoped_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        },
                    },
                ],
            }
        ],
        max_tokens=1000,
        temperature=0.0,  # Determinismo: no queremos creatividad en un auditor de datos
        response_format={"type": "json_object"},  # JSON Mode nativo de OpenAI
    )

    return response.choices[0].message.content


# Ejemplo de uso directo
if __name__ == "__main__":
    import os

    encoded, _ = encode_image_to_base64("/data/images/sample_001.jpg")

    resultado = asyncio.run(
        query_gpt4o_vision(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            base64_image=encoded,
            prompt="Describe el contenido de esta imagen en formato JSON.",
        )
    )
    print(resultado)
```

### 2.3 Inferencia con Claude: `query_claude_vision`

Esta función usa el SDK moderno de Anthropic (`anthropic>=0.20.0`), llamando a `client.messages.create` —el endpoint unificado de mensajes que reemplazó a las APIs de completion legacy. A diferencia de OpenAI, Anthropic requiere el `media_type` explícito dentro del bloque `source`, por lo que `encode_image_to_base64` resulta aún más relevante aquí.

```python
"""
vlm_anthropic_client.py
Cliente para inferencia multimodal con Claude usando el SDK >=0.20.0 de Anthropic.
Requiere: pip install "anthropic>=0.20.0"
"""

import asyncio

from anthropic import AsyncAnthropic

from vlm_utils import encode_image_to_base64

# El cliente toma la API key automáticamente desde la variable de entorno
# ANTHROPIC_API_KEY (ver docs/01_env_setup.md, Sección 4). No hardcodear la key.
client = AsyncAnthropic()


async def query_claude_vision(api_key: str, base64_image: str, prompt: str) -> str:
    """
    Envía una imagen ya codificada en Base64 junto con un prompt de texto
    a Claude y retorna la respuesta cruda del modelo como string.

    Nota de diseño: igual que en query_gpt4o_vision, esta función no conoce
    el filepath original ni el Sample de FiftyOne; solo recibe el payload
    ya codificado. Eso es exactamente el desacoplamiento descrito en la
    Sección 1.2 — el Sample nunca cruza la frontera de red.

    Args:
        api_key: API key de Anthropic. Se acepta explícitamente por claridad
            de contrato, aunque el cliente por defecto ya la resuelve desde
            la variable de entorno ANTHROPIC_API_KEY.
        base64_image: Imagen codificada en Base64 (sin el prefijo data URI).
        prompt: Instrucción de texto (system prompt o prompt de usuario)
            que acompaña a la imagen.

    Returns:
        El texto crudo devuelto por el modelo (string JSON si el modelo
        respetó las instrucciones del system prompt, pero debe tratarse
        como no confiable hasta ser parseado defensivamente).
    """
    scoped_client = AsyncAnthropic(api_key=api_key) if api_key else client

    response = await scoped_client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1000,
        temperature=0.0,  # Determinismo: no queremos creatividad en un auditor de datos
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64_image,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    return response.content[0].text


# Ejemplo de uso directo
if __name__ == "__main__":
    import os

    encoded, media_type = encode_image_to_base64("/data/images/sample_001.jpg")

    resultado = asyncio.run(
        query_claude_vision(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            base64_image=encoded,
            prompt="Describe el contenido de esta imagen en formato JSON.",
        )
    )
    print(resultado)
```

> ⚠️ **Nota de versión:** Verifica siempre el identificador de modelo vigente contra la documentación oficial del proveedor antes de la demo final. Los proveedores rotan los snapshots de modelo con frecuencia, y un identificador obsoleto provoca fallos silenciosos de la API en el peor momento posible. Si el SDK o el endpoint reportan un modelo no encontrado, consulta primero la documentación oficial vigente en lugar de asumir un nombre de memoria.

---

## 3. Prompt Engineering y Estructuración de Salidas (JSON Mode)

### 3.1 System Prompt Maestro

El siguiente *system prompt* obliga al VLM a comportarse como un **auditor de visión artificial** —objetivo, técnico y sin libertades creativas— en lugar de un asistente conversacional genérico. La instrucción de formato es deliberadamente estricta porque la fase de Acción depende de un parsing determinístico: cualquier ambigüedad aquí se traduce directamente en excepciones de `json.JSONDecodeError` más adelante.

```python
"""
prompts.py
System prompt maestro y reutilizable para análisis estructurado de imágenes.
Compartido por ambos clientes VLM (OpenAI y Anthropic) para garantizar
que la fase de Acción reciba siempre el mismo contrato de salida,
independientemente de qué proveedor respondió.
"""

SYSTEM_PROMPT_VISION_ANALYST = """
Eres un Auditor Senior de Visión Artificial integrado en un pipeline de
FiftyOne. Tu única función es analizar la imagen proporcionada y devolver
una evaluación técnica, objetiva y estructurada. No eres un asistente
conversacional: no saludes, no expliques tu razonamiento en prosa, no
agregues comentarios fuera del esquema solicitado.

REGLAS ESTRICTAS:
1. Responde EXCLUSIVAMENTE con un objeto JSON válido. No incluyas texto
   explicativo antes o después del JSON. No envuelvas la respuesta en
   bloques de markdown (no uses comillas triples de ningún tipo).
2. No inventes información que no sea visualmente verificable en la
   imagen. Si no puedes determinar un campo con certeza razonable,
   indícalo explícitamente en "rationale" en lugar de alucinar contenido.
3. Si la imagen está corrupta, borrosa, o no es analizable, indícalo en
   el campo "potential_mistake" como true y explica por qué en "rationale".
4. El campo "confidence" debe reflejar tu certeza real sobre la etiqueta
   asignada, no un valor arbitrario cercano a 1.0 por defecto.
5. El campo "potential_mistake" debe ser true si sospechas que una
   etiqueta o anotación previa del dataset podría ser incorrecta a la
   luz de lo que observas en la imagen.

Responde ÚNICAMENTE con un objeto JSON que siga EXACTAMENTE este esquema,
sin campos adicionales y sin omitir ninguno de los listados:

{
  "suggested_tags": ["string", "..."],
  "confidence": 0.0,
  "potential_mistake": false,
  "rationale": "string"
}
""".strip()
```

### 3.2 Esquema JSON Requerido

El siguiente bloque documenta el contrato exacto que la fase de Acción espera recibir, ya parseado, desde cualquiera de los dos VLMs. Mantener este esquema desacoplado del código de orquestación (Sección 4) permite versionarlo y validarlo de forma independiente si el equipo decide endurecerlo con `pydantic` más adelante.

```json
{
  "suggested_tags": ["persona", "exterior", "buena-iluminacion"],
  "confidence": 0.92,
  "potential_mistake": false,
  "rationale": "La imagen muestra una escena exterior diurna con una persona claramente visible en el centro del encuadre. La etiqueta previa 'interior' del dataset es inconsistente con la luz natural y el cielo visible en el fondo."
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `suggested_tags` | `list[str]` | Etiquetas semánticas sugeridas por el VLM, mapeables directamente a `sample.tags`. |
| `confidence` | `float (0.0–1.0)` | Certeza global del modelo sobre su propia evaluación. Se mapea al atributo `confidence` de un `fo.Classification`. |
| `potential_mistake` | `bool` | Señal de que el VLM detectó una posible inconsistencia entre la imagen y las anotaciones previas del dataset. Es el campo más valioso para *triage* de errores de etiquetado. |
| `rationale` | `str` | Justificación textual breve de por qué se asignaron esas tags y esa confianza, o por qué se marcó `potential_mistake`. Útil para auditoría humana posterior. |

> 🚧 **Advertencia técnica importante:** Los VLMs conversacionales (GPT-4o, Claude) **no garantizan localización geométrica precisa en píxeles** de forma nativa; su fuerza es la comprensión semántica, no la regresión de *bounding boxes*. Este esquema se diseñó deliberadamente sin un campo de coordenadas geométricas por esa razón. Si el reto exige detección con `bounding_box` normalizados de precisión, ese trabajo debe resolverse con un detector entrenado (YOLO, Faster R-CNN) y combinarse con el pipeline del Brain ([`docs/03_brain_curation.md`](./03_brain_curation.md)), no con el VLM conversacional.

---

## 4. Orquestación: Pipeline de Enriquecimiento en FiftyOne

Este script implementa el ciclo completo **Percepción → Razonamiento → Acción** sobre una `DatasetView` real de FiftyOne. Es intencionalmente agnóstico de proveedor en su lógica de orquestación: cambiar de Claude a GPT-4o implica sustituir una sola línea de import, no reescribir el pipeline.

```python
"""
orchestrate_vlm_to_fiftyone.py
Pipeline completo de enriquecimiento: toma una DatasetView de FiftyOne,
itera sus samples con concurrencia controlada, envía cada imagen a un VLM,
parsea la respuesta de forma defensiva, e inyecta el resultado estructurado
de vuelta en el Sample usando fo.Classification.
"""

import asyncio
import json
import logging

import fiftyone as fo

from vlm_utils import encode_image_to_base64
from vlm_anthropic_client import query_claude_vision
from prompts import SYSTEM_PROMPT_VISION_ANALYST

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vlm_orchestrator")


def parse_vlm_response(raw_response: str) -> dict:
    """
    FASE: Razonamiento (post-procesamiento).

    Parsea de forma defensiva la respuesta del VLM, manejando el caso
    en que el modelo envuelva el JSON en bloques de markdown a pesar
    de las instrucciones explícitas del system prompt. Esto ocurre con
    más frecuencia de la deseable en la práctica, por lo que nunca debe
    asumirse un string JSON limpio sin sanearlo primero.

    Args:
        raw_response: El string crudo devuelto por query_claude_vision
            o query_gpt4o_vision.

    Returns:
        Un diccionario de Python con las claves del esquema de la
        Sección 3.2 ya validadas estructuralmente.

    Raises:
        json.JSONDecodeError: si, incluso después del saneo, el contenido
            no es JSON válido. Se relanza deliberadamente en vez de
            silenciarse, para que el llamador decida cómo manejar el fallo
            (reintentar, descartar el sample, marcar para revisión manual).
    """
    cleaned = raw_response.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[len("json"):].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Fallo al parsear JSON del VLM: {e}")
        logger.error(f"Respuesta cruda recibida: {raw_response!r}")
        raise

    # Validación defensiva de claves mínimas requeridas por el esquema.
    # Preferimos rellenar con valores seguros por defecto a fallar duro
    # por un campo opcional ausente, pero seguimos registrando la anomalía.
    required_defaults = {
        "suggested_tags": [],
        "confidence": 0.0,
        "potential_mistake": False,
        "rationale": "",
    }
    for key, default_value in required_defaults.items():
        if key not in data:
            logger.warning(f"Campo '{key}' ausente en la respuesta del VLM; usando default.")
            data[key] = default_value

    return data


def inject_vlm_result_into_sample(sample: fo.Sample, vlm_data: dict) -> None:
    """
    FASE: Acción.

    Inyecta el resultado estructurado del VLM en el Sample de FiftyOne,
    usando fo.Classification como contenedor principal del veredicto
    del modelo, más los tags nativos y un campo dinámico para el detalle
    de auditoría (rationale, potential_mistake).

    Por qué fo.Classification y no un dict plano para el campo principal:
    fo.Classification es un Label nativo de FiftyOne, lo que significa que
    queda automáticamente indexado y filtrable en la App (por ejemplo,
    para construir una View de "todos los samples con confidence < 0.5").
    Un dict plano no obtendría ese tratamiento de primera clase.

    Args:
        sample: El Sample de FiftyOne a mutar. Debe pertenecer a un
            Dataset persistente para que sample.save() tenga efecto.
        vlm_data: El diccionario ya parseado y validado por
            parse_vlm_response(), siguiendo el esquema de la Sección 3.2.
    """
    # 1. Tags sugeridos -> tags nativos del Sample (sin duplicar existentes)
    existing_tags = set(sample.tags)
    new_tags = [t for t in vlm_data.get("suggested_tags", []) if t not in existing_tags]
    sample.tags.extend(new_tags)

    # 2. Veredicto principal del VLM -> fo.Classification indexable en la App
    label = "potential_mistake" if vlm_data.get("potential_mistake", False) else "verified"
    sample["vlm_audit"] = fo.Classification(
        label=label,
        confidence=float(vlm_data.get("confidence", 0.0)),
    )

    # 3. Justificación textual -> campo dinámico de texto libre, para
    #    revisión humana posterior sin necesidad de releer la imagen.
    sample["vlm_rationale"] = vlm_data.get("rationale", "")

    sample.save()  # Persistencia obligatoria del cambio en la base de datos


async def process_sample_with_vlm(sample: fo.Sample, concurrency_semaphore: asyncio.Semaphore) -> None:
    """
    Orquesta las tres fases completas para un único Sample, respetando
    el semáforo de concurrencia compartido para no exceder el rate limit
    del proveedor del VLM.

    Args:
        sample: El Sample de FiftyOne a procesar.
        concurrency_semaphore: Semáforo compartido entre todas las tareas
            de la DatasetView, limitando cuántas llamadas a la API del
            VLM están en vuelo simultáneamente.
    """
    async with concurrency_semaphore:
        filepath = sample.filepath
        logger.info(f"Procesando sample: {filepath}")

        try:
            # FASE 1: Percepción
            base64_image, _ = encode_image_to_base64(filepath)

            # FASE 2: Razonamiento
            raw_response = await query_claude_vision(
                api_key="",  # Resuelto internamente vía ANTHROPIC_API_KEY
                base64_image=base64_image,
                prompt=SYSTEM_PROMPT_VISION_ANALYST,
            )
            vlm_data = parse_vlm_response(raw_response)

            # FASE 3: Acción
            inject_vlm_result_into_sample(sample, vlm_data)

            logger.info(f"Sample {sample.id} actualizado con resultado del VLM.")

        except (FileNotFoundError, ValueError) as e:
            # Errores de la fase de Percepción: imagen ilegible o ausente.
            logger.error(f"Sample {sample.id} omitido por error de percepción: {e}")

        except json.JSONDecodeError:
            # Error de la fase de Razonamiento: el VLM devolvió contenido
            # no parseable incluso después del saneo defensivo.
            logger.error(f"Sample {sample.id} omitido por respuesta VLM no parseable.")

        except Exception as e:
            # Red de seguridad genérica: nunca dejar que un solo sample
            # con un fallo inesperado detenga el procesamiento del resto
            # de la DatasetView.
            logger.error(f"Error inesperado procesando sample {sample.id}: {e}")


async def process_view_with_vlm(view: fo.core.view.DatasetView, concurrency: int = 5) -> None:
    """
    Procesa una DatasetView completa con concurrencia controlada,
    evitando saturar el rate limit de la API del proveedor VLM.

    Por qué un semáforo y no asyncio.gather sin restricciones: enviar
    cientos de llamadas simultáneas a la API de un proveedor externo
    casi siempre dispara errores 429 (rate limit exceeded). El semáforo
    garantiza que, como máximo, `concurrency` llamadas estén en vuelo
    al mismo tiempo, sin bloquear el resto del programa.

    Args:
        view: La DatasetView de FiftyOne a procesar (puede ser el
            dataset completo o un subconjunto filtrado/saved view).
        concurrency: Número máximo de llamadas concurrentes al VLM.
    """
    semaphore = asyncio.Semaphore(concurrency)

    tareas = [
        process_sample_with_vlm(sample, semaphore)
        for sample in view
    ]

    await asyncio.gather(*tareas)


if __name__ == "__main__":
    dataset = fo.load_dataset("hackathon-dataset")

    # Procesar, por ejemplo, solo las muestras marcadas como "difíciles"
    # por el Brain (ver docs/03_brain_curation.md, Sección 5.2). Acotar
    # la View antes de llamar al VLM evita gastar cuota de API en todo
    # el dataset cuando solo interesa auditar un subconjunto.
    view_objetivo = dataset.load_saved_view("top-50-muestras-dificiles")

    asyncio.run(process_view_with_vlm(view_objetivo, concurrency=5))

    # Persistencia final a nivel de Dataset (los Sample individuales ya
    # se guardaron en cada llamada a sample.save(), pero dataset.save()
    # asegura que cualquier metadata a nivel de Dataset también se sincronice).
    dataset.save()

    print("Procesamiento VLM completado sobre la vista objetivo.")
```

### 4.1 Resumen del Flujo de Datos

| Paso | Función Responsable | Resultado |
|------|----------------------|-----------|
| Selección del subconjunto a procesar | `dataset.load_saved_view(...)` | `DatasetView` acotada (evita gastar cuota de API en todo el dataset) |
| Codificación de la imagen | `encode_image_to_base64()` | Payload Base64 + `media_type`, listo para transmisión |
| Llamada al modelo | `query_claude_vision()` / `query_gpt4o_vision()` | JSON crudo (string), no confiable hasta ser parseado |
| Parsing defensivo | `parse_vlm_response()` | `dict` de Python validado contra el esquema de la Sección 3.2 |
| Inyección en FiftyOne | `inject_vlm_result_into_sample()` | `Sample` actualizado y persistido (`sample.save()`) |
| Control de concurrencia | `asyncio.Semaphore` dentro de `process_view_with_vlm()` | Procesamiento paralelo sin exceder rate limits del proveedor |
| Persistencia final | `dataset.save()` | Sincronización de metadata a nivel de Dataset tras el batch completo |

> 🔗 **Siguiente paso en la cadena de valor:** La función `process_view_with_vlm()` es exactamente el tipo de lógica que el **Líder de Agentes** envolverá dentro de un `Operator` invocable desde la App o desde la API. Continuar en [`docs/05_agent_operators.md`](./05_agent_operators.md).

---

## Cierre de Sección

Con la integración multimodal funcionando end-to-end —desde la imagen cruda hasta el `Sample` enriquecido con clasificaciones, tags y justificaciones generadas por el VLM— el equipo tiene la base de razonamiento lista para ser expuesta como capacidades invocables del agente.

Regresar a: [`README.md`](../README.md)
