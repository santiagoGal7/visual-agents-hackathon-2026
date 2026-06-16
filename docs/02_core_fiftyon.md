# 🧬 docs/02_core_fiftyone.md — El Motor Analítico: Datasets, Views y Labels

## Hackathon Data Agents & Visual Agents | Voxel51

---

## Introducción

Este documento es el **núcleo técnico** de toda interacción con datos durante la hackathon. Si `docs/01_env_setup.md` garantiza que el entorno *existe*, este documento garantiza que el equipo **opera correctamente sobre los datos** sin destruir trabajo ajeno ni reescribir estructuras bajo presión. Todo el equipo —no solo el Ingeniero de Datos— debe dominar estos conceptos, porque tanto el Especialista en Brain como el Líder de Agentes consumirán `DatasetViews` constantemente.

Regresar a: [`README.md`](../README.md) | Anterior: [`01_env_setup.md`](./01_env_setup.md)

---

## 1. Filosofía Datasets vs. DatasetViews (El Motor Analítico)

### 1.1 La Diferencia Arquitectónica Fundamental

| Concepto              | `Dataset`                                                                                             | `DatasetView`                                                                                                                                  |
| --------------------- | ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **Persistencia**      | Físicamente almacenado en MongoDB (colección persistente).                                            | Generado **en memoria**, como resultado de una consulta o pipeline de transformaciones.                                                        |
| **Mutabilidad**       | Modificarlo (`add_samples`, `delete_samples`, editar campos) altera la base de datos permanentemente. | Es de **solo lectura sobre la estructura subyacente**: filtrar, ordenar o transformar una vista NO modifica los samples originales en MongoDB. |
| **Costo de creación** | Alto: requiere escritura en disco, indexación, persistencia.                                          | Bajo: se construye declarativamente, se evalúa de forma perezosa (*lazy evaluation*) solo cuando se itera o renderiza.                         |
| **Analogía**          | La tabla completa en una base de datos SQL.                                                           | Un `SELECT ... WHERE ... ORDER BY` ejecutado sobre esa tabla — no crea una tabla nueva, solo proyecta un resultado.                            |
| **Reversibilidad**    | Los cambios son permanentes (salvo backup/snapshot explícito).                                        | Totalmente reversible: simplemente se descarta la vista y se vuelve a consultar el `Dataset` original.                                         |

### 1.2 Por Qué Esto Es Crítico Bajo Presión de Hackathon

En un entorno de 24-48 horas, **el error más costoso es mutar el dataset base de forma irreversible** cuando lo que realmente se necesitaba era una proyección temporal de los datos. Ejemplos de fallos comunes que este principio previene:

- El Especialista en Brain necesita analizar solo las imágenes con `mistakenness > 0.7`. Si en lugar de crear una `View` filtrada, **elimina** del `Dataset` las muestras que no le interesan, el Ingeniero de Datos pierde esas muestras para su propio análisis.
- El Líder de Agentes quiere probar un Operator sobre un subconjunto pequeño de 20 imágenes. Si trunca el `Dataset` completo a 20 samples para "probar rápido", el resto del equipo pierde acceso a los datos completos.

**Regla de oro del equipo:**

> 🔒 **Todas las operaciones exploratorias, de filtrado, ordenamiento o prueba de Operators se realizan sobre `DatasetViews`. El `Dataset` original se trata como código en `main`: solo se modifica de forma deliberada y comunicada al equipo.**

```python
import fiftyone as fo

dataset = fo.load_dataset("hackathon-dataset")

# ❌ INCORRECTO bajo presión de tiempo: esto MUTA el dataset permanentemente
# dataset.delete_samples(dataset.match(F("label") == "irrelevant"))

# ✅ CORRECTO: esto crea una vista en memoria, el dataset original queda intacto
view = dataset.match(F("label") != "irrelevant")
```

---

## 2. Carga e Ingesta de Datos Eficiente

### 2.1 Crear un Dataset desde Cero Programáticamente

```python
import fiftyone as fo

# Crear (o sobrescribir) un dataset persistente con nombre explícito
dataset = fo.Dataset(name="hackathon-dataset", overwrite=True)
dataset.persistent = True  # Garantiza que sobreviva entre sesiones de Python

print(f"Dataset '{dataset.name}' creado. Persistente: {dataset.persistent}")
```

### 2.2 Ingesta Rápida con `add_samples()` — Por Qué Importa el Rendimiento

Agregar samples uno por uno mediante múltiples llamadas a `dataset.add_sample()` genera **una transacción de escritura individual a MongoDB por cada imagen**, lo cual es extremadamente costoso en I/O cuando se trabaja con cientos o miles de samples. El método `add_samples()` agrupa la inserción en **operaciones de escritura en lote (bulk write)**, reduciendo drásticamente la latencia acumulada.

```python
import fiftyone as fo
import glob

dataset = fo.load_dataset("hackathon-dataset")

# ❌ LENTO: una transacción de escritura por imagen
# for filepath in glob.glob("/data/images/*.jpg"):
#     sample = fo.Sample(filepath=filepath)
#     dataset.add_sample(sample)  # I/O individual repetido N veces

# ✅ RÁPIDO: construir todos los Sample en memoria, una sola escritura en lote
samples = [
    fo.Sample(filepath=filepath)
    for filepath in glob.glob("/data/images/*.jpg")
]

dataset.add_samples(samples)

print(f"Ingesta completada: {len(dataset)} samples agregados en una sola operación bulk.")
```

> ⚡ **Ventaja de rendimiento:** `add_samples()` serializa todos los documentos y los envía a MongoDB en una única operación `insert_many`, en lugar de N round-trips de red/disco. Para datasets de la hackathon con cientos de imágenes, esto puede significar la diferencia entre segundos y minutos de espera — tiempo que no podemos regalar.

### 2.3 Importación de Formatos Estándar (COCO y YOLO)

Si los organizadores entregan un dataset pre-anotado en formato COCO o YOLO, **no se debe parsear el JSON/TXT manualmente**. FiftyOne incluye importadores nativos optimizados vía `fo.Dataset.from_dir()`.

**Importar dataset en formato COCO:**

```python
import fiftyone as fo

dataset_coco = fo.Dataset.from_dir(
    dataset_dir="/data/hackathon_dataset_coco",
    dataset_type=fo.types.COCODetectionDataset,
    name="hackathon-coco-import",
)

print(f"Dataset COCO importado: {len(dataset_coco)} samples")
print(dataset_coco.first())
```

**Importar dataset en formato YOLO:**

```python
import fiftyone as fo

dataset_yolo = fo.Dataset.from_dir(
    dataset_dir="/data/hackathon_dataset_yolo",
    dataset_type=fo.types.YOLOv5Dataset,
    name="hackathon-yolo-import",
)

print(f"Dataset YOLO importado: {len(dataset_yolo)} samples")
print(dataset_yolo.first())
```

> 📌 **Nota técnica:** `fo.types` contiene decenas de parsers estandarizados (`VOCDetectionDataset`, `CVATImageDataset`, `TFObjectDetectionDataset`, etc.). Antes de escribir un parser custom para el formato que entreguen los organizadores, **verificar primero si ya existe soporte nativo** — es altamente probable que sí.

---

## 3. Dominio de Expresiones de Consulta (Consultas Estilo Pandas)

### 3.1 `fo.ViewField` (`F`) — El Operador de Expresiones

`ViewField`, comúnmente importado con el alias `F`, permite construir expresiones declarativas sobre los campos de un `Sample`, de forma análoga a cómo se filtran columnas en Pandas. Es el lenguaje base para **toda** consulta sobre `DatasetViews`.

```python
from fiftyone import ViewField as F
```

### 3.2 Etapas Lógicas Clave: `.match()`, `.sort_by()`, `.filter_labels()`

**`.match()` — Filtrar samples completos según una condición:**

```python
import fiftyone as fo
from fiftyone import ViewField as F

dataset = fo.load_dataset("hackathon-dataset")

# Samples cuyo campo "uniqueness" (calculado por el Brain) sea mayor a 0.8
view_unique = dataset.match(F("uniqueness") > 0.8)
```

**`.sort_by()` — Ordenar la vista según un campo o expresión:**

```python
# Ordenar por tamaño de archivo, de mayor a menor
view_sorted = dataset.sort_by(F("metadata.size_bytes"), reverse=True)
```

**`.filter_labels()` — Filtrar las etiquetas DENTRO de un campo de labels, sin descartar el sample completo:**

```python
# Mantener solo las detecciones con confianza >= 0.5 dentro del campo "predictions"
view_filtered_labels = dataset.filter_labels("predictions", F("confidence") >= 0.5)
```

> 🧠 **Diferencia clave:** `.match()` decide si el **sample entero** entra o sale de la vista. `.filter_labels()` decide qué **etiquetas individuales** dentro de un campo de labels (como `Detections`) permanecen visibles, conservando el sample aunque algunas de sus etiquetas se filtren.

### 3.3 Consulta Compleja Encadenada (Caso Real de Hackathon)

**Objetivo:** Filtrar muestras con resolución mayor a 1080p, que contengan al menos una detección de la clase `"person"` con `confidence < 0.4` (posibles falsos positivos del modelo), y ordenar el resultado por tamaño de archivo.

```python
import fiftyone as fo
from fiftyone import ViewField as F

dataset = fo.load_dataset("hackathon-dataset")

# Paso 1: Filtrar samples con resolución mayor a 1080p (height > 1080)
# Paso 2: Quedarse solo con samples que tengan AL MENOS UNA detección
#         de clase "person" con confidence < 0.4
# Paso 3: Ordenar el resultado final por tamaño de archivo (bytes)

view_falsos_positivos_hd = (
    dataset
    .match(F("metadata.height") > 1080)
    .match(
        F("predictions.detections").filter(
            (F("label") == "person") & (F("confidence") < 0.4)
        ).length() > 0
    )
    .sort_by(F("metadata.size_bytes"))
)

print(f"Muestras candidatas a revisión de falsos positivos: {len(view_falsos_positivos_hd)}")

# Iterar para inspección rápida en consola
for sample in view_falsos_positivos_hd.limit(5):
    print(sample.filepath, sample.metadata.size_bytes)
```

> 💡 **Explicación de la expresión anidada:** `F("predictions.detections").filter(...)` opera sobre la lista de detecciones dentro de cada sample, aplicando la condición compuesta `(label == "person") & (confidence < 0.4)`. El `.length() > 0` final convierte ese filtrado interno en una condición booleana usable por `.match()`: "¿sobrevivió al menos una detección sospechosa?".

---

## 4. Anatomía Teórica y Práctica de Labels (Estructuras de Etiquetas)

FiftyOne estandariza las anotaciones mediante clases de `Label` fuertemente tipadas. Conocer su estructura exacta es indispensable para que el Especialista en Brain y el Líder de Agentes inyecten resultados de modelos (VLMs, detectores, segmentadores) de forma compatible con el resto del pipeline.

### 4.1 `fo.Classification` — Etiquetas Globales de Imagen

Usado para una etiqueta única que describe la imagen completa (ej. salida de un clasificador o de un VLM respondiendo "¿qué hay en esta imagen?").

```python
import fiftyone as fo

sample = dataset.first()

sample["scene_classification"] = fo.Classification(
    label="outdoor_urban_scene",
    confidence=0.93,
)

sample.save()  # Obligatorio: persiste el cambio del Sample en MongoDB
```

### 4.2 `fo.Detections` — Cajas Delimitadoras (Bounding Boxes)

Usado para localización de objetos. **Formato normalizado obligatorio:** `[top-left-x, top-left-y, width, height]`, con todos los valores expresados como **fracciones entre 0 y 1** relativas a las dimensiones de la imagen (no píxeles absolutos).

```python
import fiftyone as fo

sample = dataset.first()

deteccion_persona = fo.Detection(
    label="person",
    # [x_top_left, y_top_left, width, height] -- todos normalizados [0, 1]
    bounding_box=[0.21, 0.15, 0.30, 0.55],
    confidence=0.87,
)

deteccion_bicicleta = fo.Detection(
    label="bicycle",
    bounding_box=[0.55, 0.40, 0.20, 0.25],
    confidence=0.76,
)

sample["predictions"] = fo.Detections(
    detections=[deteccion_persona, deteccion_bicicleta]
)

sample.save()
```

> 📐 **Por qué normalizado:** Al usar coordenadas relativas (0 a 1) en lugar de píxeles absolutos, las anotaciones son **independientes de la resolución de la imagen**. Esto permite comparar, transformar o re-escalar imágenes sin tener que recalcular las cajas — crítico cuando el dataset de la hackathon mezcla imágenes de distintas resoluciones.

### 4.3 `fo.Segmentation` y `fo.Polylines` — Máscaras y Segmentación de Instancias

**`fo.Polylines`** — para contornos vectoriales (segmentación de instancia ligera, sin necesidad de máscaras rasterizadas):

```python
import fiftyone as fo

contorno_objeto = fo.Polyline(
    label="person",
    points=[[
        (0.20, 0.15), (0.45, 0.15), (0.50, 0.60), (0.18, 0.65),
    ]],  # Lista de listas de puntos normalizados (x, y), permite múltiples shapes
    closed=True,
    filled=True,
)

sample["instance_outlines"] = fo.Polylines(polylines=[contorno_objeto])
sample.save()
```

**`fo.Segmentation`** — para máscaras de segmentación semántica a nivel de píxel, almacenadas como arrays de NumPy:

```python
import fiftyone as fo
import numpy as np

# Máscara de ejemplo: array 2D donde cada valor entero representa una clase
# (0 = fondo, 1 = clase A, 2 = clase B, etc.)
mascara = np.zeros((480, 640), dtype=np.uint8)
mascara[100:300, 150:400] = 1  # Región asignada a la clase con índice 1

sample["semantic_mask"] = fo.Segmentation(mask=mascara)
sample.save()
```

> 🎯 **Criterio de selección:** Usar `Polylines` cuando el modelo (o el VLM) entrega contornos vectoriales ligeros y se prioriza velocidad de renderizado en la App. Usar `Segmentation` cuando el reto requiere máscaras densas a nivel de píxel (ej. segmentación semántica de un modelo tipo SAM o DeepLab).

---

## 5. Persistencia e Interfaz (Saved Views & App Sync)

### 5.1 Guardar una Vista Lógica con `dataset.save_view()`

Una `DatasetView` construida en código es efímera por defecto: vive solo en la sesión de Python actual. Para que **cualquier integrante del equipo** pueda abrir la App y ver esa misma vista filtrada sin reescribir el código, se debe guardar como **Saved View**.

```python
import fiftyone as fo
from fiftyone import ViewField as F

dataset = fo.load_dataset("hackathon-dataset")

vista_falsos_positivos = dataset.match(
    F("predictions.detections").filter(
        (F("label") == "person") & (F("confidence") < 0.4)
    ).length() > 0
)

dataset.save_view(
    "posibles-falsos-positivos-person",
    vista_falsos_positivos,
    description="Detecciones de 'person' con confidence < 0.4, candidatas a revisión manual.",
)

print("Vista guardada. Disponible ahora en el selector de vistas de la App.")
```

> 🔁 **Beneficio directo para el equipo:** Una vez guardada, la vista aparece en el **dropdown de Saved Views dentro de la App de FiftyOne** (puerto `5151`), accesible para todos sin necesidad de ejecutar código Python. Esto es clave para que el equipo de Brain comparta hallazgos directamente con el Líder de Agentes sin fricción.

### 5.2 Lanzar la App Vinculada a un Dataset o Vista Específica

```python
import fiftyone as fo

dataset = fo.load_dataset("hackathon-dataset")

# Opción A: lanzar la App apuntando al dataset completo
session = fo.launch_app(dataset)

# Opción B: lanzar la App apuntando directamente a una vista filtrada
vista_hd_falsos_positivos = dataset.load_saved_view("posibles-falsos-positivos-person")
session = fo.launch_app(vista_hd_falsos_positivos)

# La sesión queda activa en el puerto 5151 (ver Tabla de Puertos en el README)
print(f"App de FiftyOne corriendo en: {session.url}")
```

> 🌐 **Recordatorio de puertos:** La App se sirve por defecto en `http://localhost:5151`, tal como se especifica en la [Tabla de Puertos y Servicios Estándar](../README.md#5-tabla-de-puertos-y-servicios-estándar) del README principal.

---

## Cierre de Sección

Con el dominio de `Datasets`, `DatasetViews`, expresiones `ViewField` y la anatomía de `Labels`, el equipo cuenta con la base analítica necesaria para que el Especialista en Brain calcule `embeddings` y `mistakenness` sobre vistas correctamente curadas. Continuar en [`docs/03_brain_embeddings.md`](./03_brain_embeddings.md).

Regresar a: [`README.md`](../README.md)
