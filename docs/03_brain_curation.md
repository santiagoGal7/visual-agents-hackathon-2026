# 🧠 docs/03_brain_curation.md — Curación Data-Centric con FiftyOne Brain

## Hackathon Data Agents & Visual Agents | Voxel51

---

## Introducción

Si `docs/02_core_fiftyone.md` enseñó al equipo a **estructurar y consultar** datos, este documento enseña a **auditar y priorizar** esos datos sin intervención manual. `fiftyone.brain` (importado convencionalmente como `fob`) es el motor analítico que convierte un dataset crudo en un dataset **inteligente**: capaz de señalar sus propios errores, sus propios duplicados y sus propias muestras más informativas. Esta capacidad es la que el agente visual consumirá como input de decisión.

Regresar a: [`README.md`](../README.md) | Anterior: [`02_core_fiftyone.md`](./02_core_fiftyone.md)

---

## 1. Filosofía de Curación Data-Centric con FiftyOne Brain

### 1.1 Analizar la Geometría de los Datos Sin Anotaciones

El paradigma **Data-Centric AI** parte de una premisa incómoda pero correcta: **la mayoría de los errores de un sistema de visión artificial no están en el modelo, están en los datos**. `fiftyone.brain` opera sobre esta premisa proyectando cada imagen (o cada label) a un espacio vectorial de alta dimensión —los **embeddings**— y analizando su geometría: distancias, densidades, vecinos cercanos, outliers.

Lo crítico es que este análisis **no requiere etiquetas humanas previas** para funcionar en su forma más básica (embeddings, uniqueness). Solo cuando se quiere auditar la *calidad* de etiquetas ya existentes (mistakenness) se necesitan también las predicciones de un modelo. Esto significa que el equipo puede empezar a encontrar **estructura, duplicados y outliers** en el dataset de la hackathon **desde el primer minuto**, incluso antes de tener un detector o un VLM funcionando.

### 1.2 Por Qué Esto Es Decisivo en un Entorno de Hackathon

| Problema típico de hackathon                                                                                    | Solución que ofrece el Brain                                                                              |
| --------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| El dataset entregado por los organizadores tiene miles de imágenes; no hay tiempo de revisarlas una por una.    | `compute_uniqueness()` y `compute_visualization()` exponen visualmente clusters y outliers en minutos.    |
| Las etiquetas pre-existentes (si las hay) pueden tener errores que arruinen las métricas del modelo del equipo. | `compute_mistakenness()` aísla automáticamente las muestras con mayor probabilidad de error de anotación. |
| El equipo necesita encontrar "la foto de un carro bajo la lluvia" sin saber su nombre de archivo.               | `compute_similarity()` + búsqueda en lenguaje natural sobre embeddings tipo CLIP.                         |
| No hay tiempo de etiquetar todo el dataset para entrenar/ajustar un modelo.                                     | `compute_hardness()` prioriza qué muestras son más valiosas para revisión o fine-tuning.                  |

> 🎯 **Tesis central del equipo:** El Brain no es un "extra" — es la capa que transforma horas de revisión manual en **segundos de consulta programática**. Cada hora ganada aquí es una hora disponible para el agente y la API.

---

## 2. Cálculo y Visualización de Embeddings Interactivos (UMAP)

### 2.1 Cálculo de Embeddings con CLIP (Model Zoo)

FiftyOne integra modelos estándar de la industria directamente desde su **Model Zoo**, evitando que el equipo tenga que descargar y orquestar pesos manualmente.

```python
import fiftyone as fo
import fiftyone.brain as fob
import fiftyone.zoo as foz

dataset = fo.load_dataset("hackathon-dataset")

# Cargar el modelo CLIP desde el Model Zoo de FiftyOne
modelo_clip = foz.load_zoo_model("clip-vit-base-patch32")

# Calcular embeddings para TODAS las muestras del dataset
# y almacenarlos directamente como un campo del Sample
dataset.compute_embeddings(
    model=modelo_clip,
    embeddings_field="clip_embeddings",
)

print("Embeddings CLIP calculados y almacenados en 'clip_embeddings'.")
```

> ⚙️ **Nota de rendimiento:** `compute_embeddings()` procesa el dataset en batches internamente. Si el equipo tiene GPU disponible, FiftyOne la detecta automáticamente vía PyTorch/Torch backend del modelo Zoo, acelerando el cómputo de forma transparente.

### 2.2 Reducción de Dimensionalidad con UMAP

Los embeddings de CLIP viven en un espacio de **512 dimensiones**, imposible de visualizar directamente. `fob.compute_visualization()` proyecta ese espacio a 2D (o 3D) usando UMAP, preservando la estructura de vecindad local — es decir, imágenes semánticamente similares quedan **espacialmente cercanas** en el plano 2D.

```python
import fiftyone as fo
import fiftyone.brain as fob

dataset = fo.load_dataset("hackathon-dataset")

resultados_visualizacion = fob.compute_visualization(
    dataset,
    embeddings="clip_embeddings",   # Reutiliza los embeddings ya calculados
    method="umap",
    brain_key="clip_umap_viz",      # Identificador para recuperar este resultado después
    num_dims=2,
)

print("Proyección UMAP 2D calculada y almacenada bajo brain_key='clip_umap_viz'.")
```

### 2.3 Explorando el Embeddings Panel en la App

Una vez calculada la visualización, el equipo puede explorarla **interactivamente** dentro de la App de FiftyOne (puerto `5151`):

```python
import fiftyone as fo

dataset = fo.load_dataset("hackathon-dataset")
session = fo.launch_app(dataset)
```

**Pasos para usar el Embeddings Panel:**

| Paso | Acción en la App                                                                                                                                                                                                   |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1    | Dentro de la interfaz web, abrir el panel lateral y seleccionar **"+ Embeddings"** para añadir el panel de visualización.                                                                                          |
| 2    | En el selector superior del panel, elegir el `brain_key` calculado: `clip_umap_viz`.                                                                                                                               |
| 3    | La App renderiza un scatter plot 2D interactivo: cada punto es una imagen del dataset proyectada por UMAP.                                                                                                         |
| 4    | Usar la herramienta de **selección por lazo (lasso)** del panel para encerrar visualmente un clúster de puntos.                                                                                                    |
| 5    | La selección se sincroniza automáticamente con el grid principal de muestras: solo se muestran las imágenes del clúster seleccionado.                                                                              |
| 6    | Desde ahí, se puede guardar esa selección como una `Saved View` (ver [`02_core_fiftyone.md`](./02_core_fiftyone.md#51-guardar-una-vista-lógica-con-datasetsave_view)) para que el resto del equipo la inspeccione. |

> 💡 **Caso de uso típico en hackathon:** Si en el scatter plot aparece un clúster denso y aislado del resto, es altamente probable que sean **imágenes casi duplicadas** o una sub-categoría no etiquetada explícitamente — información crítica para decidir cómo entrenar o evaluar el sistema.

---

## 3. Auditoría Automática de Etiquetas (Algoritmo de Mistakenness)

### 3.1 Lógica del Algoritmo

`fob.compute_mistakenness()` no solo compara "¿la predicción coincide con la etiqueta?" de forma binaria. Analiza la **distribución de probabilidad completa (logits/softmax)** que el modelo genera para cada muestra, y la contrasta contra la etiqueta humana (ground truth) ya existente.

La intuición detrás del algoritmo es la siguiente:

- Si el modelo predice la clase correcta con **alta confianza** y coincide con el ground truth → la etiqueta es probablemente correcta.
- Si el modelo predice una clase **distinta** al ground truth, pero lo hace con **alta confianza y consistencia** → es una señal fuerte de que el **ground truth podría estar mal etiquetado**, no que el modelo se equivocó.
- Si el modelo está genuinamente confundido (distribución de probabilidad plana, sin clase dominante) → es más probable que sea un caso ambiguo o difícil, no necesariamente un error de etiqueta.

El resultado es un score continuo de `mistakenness` por muestra: mientras más alto, mayor la probabilidad de que la **anotación original**, no el modelo, sea la fuente del error.

### 3.2 Cómputo de Mistakenness y Aislamiento de las 100 Muestras Más Sospechosas

**Prerrequisito:** el dataset debe tener un campo de `ground_truth` (etiquetas originales) y un campo de `predictions` (salida de un modelo, con `confidence`/`logits` disponibles).

```python
import fiftyone as fo
import fiftyone.brain as fob

dataset = fo.load_dataset("hackathon-dataset")

# Calcular mistakenness comparando "ground_truth" contra "predictions"
fob.compute_mistakenness(
    dataset,
    pred_field="predictions",
    label_field="ground_truth",
    mistakenness_field="mistakenness",  # Campo donde se almacena el score resultante
)

# Aislar en una DatasetView las 100 muestras con mayor score de mistakenness
view_top_100_sospechosas = (
    dataset
    .sort_by("mistakenness", reverse=True)
    .limit(100)
)

print(f"Top 100 muestras candidatas a error de anotación aisladas.")
print(f"Score más alto: {view_top_100_sospechosas.first().mistakenness:.4f}")

# Guardar la vista para revisión colaborativa en la App
dataset.save_view(
    "top-100-posibles-errores-anotacion",
    view_top_100_sospechosas,
    description="Top 100 muestras con mayor mistakenness — candidatas a re-etiquetado.",
)
```

> ⚠️ **Importante:** `compute_mistakenness()` requiere que el campo de `predictions` contenga **logits o vectores de confianza completos**, no solo la etiqueta final predicha. Si el modelo del equipo solo entrega `argmax`, la calidad de la métrica se degrada — se recomienda exponer la distribución completa de probabilidad al guardar las predicciones (ver [`fo.Classification`](./02_core_fiftyone.md#41-foclassification--etiquetas-globales-de-imagen) con el parámetro `logits`).

---

## 4. Búsqueda Semántica por Similitud Visual y Texto

### 4.1 Inicializar un Índice de Similitud

`fob.compute_similarity()` construye un índice vectorial en memoria (o backend externo, si se configura) a partir de los embeddings ya calculados, habilitando búsquedas de vecinos más cercanos de forma eficiente.

```python
import fiftyone as fo
import fiftyone.brain as fob

dataset = fo.load_dataset("hackathon-dataset")

fob.compute_similarity(
    dataset,
    embeddings="clip_embeddings",
    brain_key="clip_similarity_index",
    model="clip-vit-base-patch32",  # Necesario para habilitar búsquedas por texto (ver 4.3)
)

print("Índice de similitud semántica construido bajo brain_key='clip_similarity_index'.")
```

> 🔑 **Por qué se especifica `model` aquí:** Pasar el modelo CLIP explícitamente le indica al índice cómo **codificar futuras consultas de texto** al mismo espacio vectorial que las imágenes, habilitando la búsqueda *texto → imagen* de la Sección 4.3.

### 4.2 Búsqueda por Similitud Visual (Imagen → Imágenes Similares)

```python
import fiftyone as fo

dataset = fo.load_dataset("hackathon-dataset")

# Tomar un sample de referencia (por ejemplo, una imagen con un error detectado)
sample_referencia = dataset.first()
sample_id = sample_referencia.id

# Encontrar las 10 imágenes más visualmente similares en el espacio de embeddings
view_similares = dataset.sort_by_similarity(
    sample_id,
    k=10,
    brain_key="clip_similarity_index",
)

for sample in view_similares:
    print(sample.filepath)
```

### 4.3 Búsqueda Semántica en Lenguaje Natural (Texto → Imágenes)

Esta es la capacidad que habilita a un **agente conversacional** a consultar el dataset usando lenguaje natural, sin necesidad de conocer IDs ni metadata exacta.

```python
import fiftyone as fo

dataset = fo.load_dataset("hackathon-dataset")

# Consulta en lenguaje natural directamente sobre el índice CLIP
view_busqueda_texto = dataset.sort_by_similarity(
    "a photo of a car in the rain",
    k=5,
    brain_key="clip_similarity_index",
)

for sample in view_busqueda_texto:
    print(sample.filepath)
```

> 🤖 **Conexión directa con el Agente:** Esta función es, en esencia, el "Skill de búsqueda semántica" que el **Líder de Agentes** expondrá como un `Operator` (ver [`docs/05_agent_operators.md`](./05_agent_operators.md)). El prompt del usuario final se pasa tal cual a `sort_by_similarity()`, y el resultado se renderiza directamente en la App.

---

## 5. Minería de Muestras Críticas (Uniqueness y Hardness)

### 5.1 `fob.compute_uniqueness()` — Detección de Outliers y Duplicados

`compute_uniqueness()` asigna a cada muestra un score basado en qué tan **aislada o redundante** es respecto al resto del dataset en el espacio de embeddings. Un score de uniqueness **bajo** sugiere que existen muchas muestras casi idénticas (candidatas a deduplicación); un score **alto** sugiere una muestra atípica o un outlier potencialmente valioso (o problemático).

```python
import fiftyone as fo
import fiftyone.brain as fob

dataset = fo.load_dataset("hackathon-dataset")

fob.compute_uniqueness(
    dataset,
    embeddings="clip_embeddings",
    uniqueness_field="uniqueness",
)

# Muestras MENOS únicas -> candidatas a duplicados/redundancia
view_duplicados_potenciales = dataset.sort_by("uniqueness").limit(20)

# Muestras MÁS únicas -> outliers potencialmente interesantes (o ruido)
view_outliers = dataset.sort_by("uniqueness", reverse=True).limit(20)

print(f"Posibles duplicados (uniqueness más bajo): {len(view_duplicados_potenciales)}")
print(f"Posibles outliers (uniqueness más alto): {len(view_outliers)}")
```

### 5.2 `fob.compute_hardness()` — Priorización de Muestras para el Agente

`compute_hardness()` cuantifica qué tan **difícil o ambigua** es una muestra para el modelo actual, basándose en la incertidumbre de su distribución de predicción. Las muestras "duras" son las que más valor aportan si se priorizan para revisión humana, fine-tuning, o como casos de prueba exigentes para el agente visual.

```python
import fiftyone as fo
import fiftyone.brain as fob

dataset = fo.load_dataset("hackathon-dataset")

# Requiere un campo de predicciones con distribución de confianza (logits/softmax)
fob.compute_hardness(
    dataset,
    label_field="predictions",
    hardness_field="hardness",
)

# Aislar el top de muestras más difíciles para priorizar en el agente
view_muestras_dificiles = dataset.sort_by("hardness", reverse=True).limit(50)

dataset.save_view(
    "top-50-muestras-dificiles",
    view_muestras_dificiles,
    description="Muestras con mayor hardness — prioridad para revisión y testing del agente.",
)

print(f"Top 50 muestras difíciles aisladas y guardadas como Saved View.")
```

### 5.3 Tabla Resumen de Métricas del Brain

| Métrica               | Función                                            | Requiere Predicciones | Pregunta que Responde                                        |
| --------------------- | -------------------------------------------------- | --------------------- | ------------------------------------------------------------ |
| **Embeddings + UMAP** | `compute_embeddings()` + `compute_visualization()` | No                    | "¿Cómo se agrupan visualmente mis datos?"                    |
| **Similarity**        | `compute_similarity()`                             | No (solo embeddings)  | "¿Qué imágenes son similares a esta, o a este texto?"        |
| **Mistakenness**      | `compute_mistakenness()`                           | Sí                    | "¿Qué etiquetas probablemente están mal anotadas?"           |
| **Uniqueness**        | `compute_uniqueness()`                             | No                    | "¿Qué muestras son outliers o duplicados?"                   |
| **Hardness**          | `compute_hardness()`                               | Sí                    | "¿Qué muestras son más ambiguas o difíciles para el modelo?" |

---

## Cierre de Sección

Con el dataset auditado mediante embeddings, mistakenness, similarity, uniqueness y hardness, el equipo cuenta con **señales de calidad accionables** listas para alimentar tanto al VLM ([`docs/04_vlm_integration.md`](./04_vlm_integration.md)) como a los Operators del agente ([`docs/05_agent_operators.md`](./05_agent_operators.md)).

Regresar a: [`README.md`](../README.md)
