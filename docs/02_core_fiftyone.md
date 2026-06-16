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

`...`

---

## Cierre de Sección

Con el dominio de `Datasets`, `DatasetViews`, expresiones `ViewField` y la anatomía de `Labels`, el equipo cuenta con la base analítica necesaria para que el Especialista en Brain calcule `embeddings` y `mistakenness` sobre vistas correctamente curadas. Continuar en [`docs/03_brain_embeddings.md`](./03_brain_embeddings.md).

Regresar a: [`README.md`](../README.md)
