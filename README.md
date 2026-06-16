# 🚀 FiftyOne Visual Agents Hackathon — Centro de Mando Técnico

## Hackathon Data Agents & Visual Agents | Voxel51 | 19 de Junio, 2026

---

## 1. Introducción y Misión del Proyecto

Bienvenido al repositorio raíz de nuestra incursión en la **Hackathon de Data Agents & Visual Agents**, impulsada por **Voxel51**. Este documento es el **punto único de verdad (Single Source of Truth)** para la coordinación técnica del equipo durante las 24-48 horas críticas de desarrollo.

Nuestra tesis de combate se fundamenta en **Data-Centric AI (DCAI)**: en un mundo donde los modelos pre-entrenados y los LLMs/VLMs son commodities, la ventaja competitiva real reside en la **calidad, curación y observabilidad del dato visual**. No vamos a construir "otro wrapper de un modelo". Vamos a construir un **Agente Visual Inteligente** capaz de razonar sobre datasets usando el ecosistema **FiftyOne**, identificando *mistakenness*, gestionando *embeddings* y exponiendo esa inteligencia a través de *Operators* y *Skills* reutilizables.

| Atributo                    | Detalle                                                    |
| --------------------------- | ---------------------------------------------------------- |
| **Evento**                  | Hackathon Data Agents & Visual Agents                      |
| **Organizador**             | Voxel51                                                    |
| **Fecha límite de entrega** | 19 de Junio, 2026                                          |
| **Stack Core**              | FiftyOne, FiftyOne Brain, Operators/Plugins SDK            |
| **Paradigma rector**        | Data-Centric AI (DCAI)                                     |
| **Filosofía de equipo**     | Velocidad sin caos. Documentación primero, código después. |

> **Principio no negociable:** Si no está documentado en `docs/`, no existe para el equipo de jueces ni para tus compañeros. Cada decisión arquitectónica relevante se registra, no se asume.

---

## 2. Arquitectura General del Repositorio

La carpeta `docs/` es el **mapa de ruta obligatorio** para cualquier miembro del equipo, nuevo colaborador, o juez técnico que evalúe nuestra entrega. Cada archivo resuelve un problema operativo específico y debe mantenerse actualizado en tiempo real conforme avanza el desarrollo.

| #   | Archivo                                                                | Problema que Resuelve                                                                                                                                                                                                    | Responsable Sugerido               |
| --- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------- |
| 01  | [`docs/01_env_setup.md`](./docs/01_env_setup.md)                       | Elimina el "funciona en mi máquina". Estandariza instalación de FiftyOne, dependencias Python, variables de entorno (API keys de VLMs) y versión de MongoDB local requerida.                                             | Desarrollador de Integración y API |
| 02  | [`docs/02_dataset_architecture.md`](./docs/02_dataset_architecture.md) | Define el esquema del `Dataset`, convenciones de `Sample fields`, estructura de `DatasetViews` reutilizables y estrategia de versionado/snapshot de datos.                                                               | Ingeniero de Datos e Ingesta       |
| 03  | [`docs/03_brain_embeddings.md`](./docs/03_brain_embeddings.md)         | Documenta la estrategia de cómputo de `embeddings` (CLIP u otros), configuración de índices de similitud y el pipeline de `Mistakenness`/`Uniqueness` del FiftyOne Brain.                                                | Especialista en Visión y Brain     |
| 04  | [`docs/04_vlm_integration.md`](./docs/04_vlm_integration.md)           | Detalla cómo se conectan los VLMs externos (GPT-4o, Claude) al pipeline: prompting, parsing de respuestas, mapeo a `Labels` de FiftyOne y manejo de rate limits/costos.                                                  | Especialista en Visión y Brain     |
| 05  | [`docs/05_agent_operators.md`](./docs/05_agent_operators.md)           | Especifica la arquitectura de **Operators y Plugins**: contratos de entrada/salida, registro en el `Operator Registry`, y cómo cada "Skill" del agente se traduce en una acción ejecutable dentro de la App de FiftyOne. | Líder de Agentes y Extensibilidad  |
| 06  | [`docs/06_api_deployment.md`](./docs/06_api_deployment.md)             | Cubre la capa de orquestación: endpoints de FastAPI, contrato de la API REST/WebSocket, estrategia de despliegue rápido (Docker/local) y checklist de demo en vivo.                                                      | Desarrollador de Integración y API |

> 📌 **Regla de oro:** Ningún Pull Request a `main` se aprueba si modifica funcionalidad sin actualizar el archivo correspondiente en `docs/`. La documentación desincronizada es deuda técnica que no podemos pagar bajo presión de tiempo.

---

## 3. Definición de Roles de Combate (Equipo de 4)

Cada rol tiene **soberanía técnica** sobre su dominio, pero la integración final es responsabilidad colectiva. La claridad de roles es lo que nos permite paralelizar sin pisarnos.

| Rol                                    | Responsable | Dominio Técnico                                                                                                                                        | Entregables Clave                                                                                                     | Documento Maestro                                                                                                             |
| -------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Líder de Agentes y Extensibilidad**  | Tú          | Diseño de `Operators`, `Skills`, arquitectura de plugins, contratos de invocación del agente, orquestación de la lógica de decisión del agente visual. | Catálogo de Operators funcionando, esquema de Skills documentado, demo de invocación agente → acción en FiftyOne App. | [`docs/05_agent_operators.md`](./docs/05_agent_operators.md)                                                                  |
| **Ingeniero de Datos e Ingesta**       | —           | Carga de datasets, manipulación de `DatasetViews`, limpieza de datos en memoria, transformaciones, deduplicación, validación de esquemas de `Sample`.  | Pipeline de ingesta reproducible, vistas (`Views`) curadas y reutilizables, dataset limpio y versionado.              | [`docs/02_dataset_architecture.md`](./docs/02_dataset_architecture.md)                                                        |
| **Especialista en Visión y Brain**     | —           | Integración de VLMs (GPT-4o / Claude), cómputo de `embeddings` (CLIP), detección de errores con `Mistakenness`, análisis de `Uniqueness` y `Hardness`. | Embeddings indexados, scores de Mistakenness calculados, integración VLM funcional con etiquetado automático.         | [`docs/03_brain_embeddings.md`](./docs/03_brain_embeddings.md) · [`docs/04_vlm_integration.md`](./docs/04_vlm_integration.md) |
| **Desarrollador de Integración y API** | —           | Orquestación de FastAPI, configuración de entorno local, conexión Frontend↔Backend↔FiftyOne, despliegue rápido del prototipo para demo.                | API REST operativa, entorno reproducible con un solo comando, prototipo desplegado y accesible para el jurado.        | [`docs/01_env_setup.md`](./docs/01_env_setup.md) · [`docs/06_api_deployment.md`](./docs/06_api_deployment.md)                 |

### Matriz de Dependencias entre Roles

| De → Hacia                | Ingeniero de Datos                                 | Especialista en Brain                        | Líder de Agentes                                   | Dev. Integración                           |
| ------------------------- | -------------------------------------------------- | -------------------------------------------- | -------------------------------------------------- | ------------------------------------------ |
| **Ingeniero de Datos**    | —                                                  | Provee `Dataset` limpio y `Views` base       | Provee esquema de campos para diseñar Operators    | Provee dataset para exponer vía API        |
| **Especialista en Brain** | Consume `Views` para indexar embeddings            | —                                            | Provee scores de Mistakenness como input de Skills | Expone resultados de Brain como endpoints  |
| **Líder de Agentes**      | Solicita nuevas `Views` según necesidad del agente | Consume embeddings/mistakenness en Operators | —                                                  | Define contrato de invocación para FastAPI |
| **Dev. Integración**      | Consulta estado del dataset vía API                | Expone resultados de Brain                   | Expone Operators como endpoints ejecutables        | —                                          |

---

## 4. Git Workflow de Emergencia (Protocolo de Ramas)

Bajo presión de tiempo, **el caos en Git es el enemigo silencioso número uno**. Este protocolo es estricto y no admite improvisación. Cada rol trabaja en su rama dedicada y converge en `main` mediante Pull Requests revisados, nunca con `push --force` directo a `main`.

### 4.1 Estructura de Ramas

| Rama           | Propietario                        | Propósito                                                             |
| -------------- | ---------------------------------- | --------------------------------------------------------------------- |
| `main`         | Equipo completo                    | Rama estable, siempre desplegable. Solo se actualiza vía PR aprobado. |
| `feat/dataset` | Ingeniero de Datos e Ingesta       | Manipulación de `DatasetViews`, limpieza, ingesta.                    |
| `feat/brain`   | Especialista en Visión y Brain     | Embeddings, Mistakenness, integración VLM.                            |
| `feat/agent`   | Líder de Agentes y Extensibilidad  | Operators, Skills, lógica de plugins.                                 |
| `feat/api`     | Desarrollador de Integración y API | FastAPI, entorno, despliegue.                                         |

### 4.2 Reglas de Sincronización

1. **Nunca trabajar directamente sobre `main`.** Toda funcionalidad nace en la rama de rol correspondiente.
2. **Sincronizar contra `main` cada 2 horas como mínimo:**
   
   ```bash
   git checkout feat/tu-rama
   git fetch origin
   git rebase origin/main
   ```
3. **Commits atómicos y descriptivos** usando el prefijo del rol:
   
   ```bash
   git commit -m "feat(agent): registrar Operator de deteccion de mistakenness"
   ```
4. **Pull Request obligatorio** antes de fusionar a `main`. Mínimo un revisor distinto al autor.
5. **Nunca usar `git push --force` sobre `main`.** Si es estrictamente necesario en tu propia rama, usar `--force-with-lease`.

### 4.3 Protocolo de Resolución de Merge Conflicts (Comandos Básicos)

Cuando un conflicto aparece al fusionar o rebasar, sigue esta secuencia sin pánico:

```bash
# 1. Identificar los archivos en conflicto
git status

# 2. Abrir cada archivo marcado y resolver manualmente
#    Buscar los marcadores: <<<<<<<, =======, >>>>>>>
#    Conservar la lógica correcta, eliminar los marcadores

# 3. Marcar el archivo como resuelto
git add <archivo-resuelto>

# 4. Si estabas en rebase, continuar:
git rebase --continue

# 4b. Si estabas en merge, finalizar el commit:
git commit

# 5. Verificar que todo compile/funcione antes de subir
git push origin feat/tu-rama --force-with-lease
```

> ⚠️ **Regla de pánico:** Si el conflicto involucra lógica que no entiendes (por ejemplo, código de otro rol), **detente y pregunta en el canal del equipo antes de resolver a ciegas**. Un merge mal resuelto bajo presión es más costoso que 5 minutos de coordinación.

| Situación                                                        | Comando de Rescate                |
| ---------------------------------------------------------------- | --------------------------------- |
| Quiero abortar un rebase conflictivo y volver al estado anterior | `git rebase --abort`              |
| Quiero abortar un merge conflictivo                              | `git merge --abort`               |
| Necesito ver las diferencias exactas del conflicto               | `git diff`                        |
| Quiero descartar cambios locales y traer la versión remota       | `git checkout --theirs <archivo>` |
| Quiero conservar mi versión local en el conflicto                | `git checkout --ours <archivo>`   |

---

## 5. Tabla de Puertos y Servicios Estándar

Toda máquina del equipo debe respetar esta asignación de puertos para garantizar que las demos, integraciones y pruebas cruzadas funcionen sin fricción entre estaciones de trabajo.

| Servicio           | Puerto  | Descripción                                                                                          | Comando de Verificación      |
| ------------------ | ------- | ---------------------------------------------------------------------------------------------------- | ---------------------------- |
| **MongoDB**        | `27017` | Base de datos backend nativa de FiftyOne. Almacena metadatos de datasets, samples y labels.          | `mongosh --port 27017`       |
| **FiftyOne App**   | `5151`  | Interfaz visual interactiva de FiftyOne para exploración de datasets, Views y resultados del Brain.  | `http://localhost:5151`      |
| **FastAPI**        | `8000`  | Capa de orquestación REST que expone los Operators del agente y resultados del pipeline al frontend. | `http://localhost:8000/docs` |
| **React Frontend** | `5173`  | Interfaz de usuario del agente (si aplica), consumiendo la API de FastAPI vía Vite Dev Server.       | `http://localhost:5173`      |

> 🔒 **Nota de infraestructura:** Si dos servicios colisionan en el mismo puerto durante el desarrollo local, **nunca cambies el puerto estándar**: documenta el conflicto en `docs/01_env_setup.md` y resuélvelo mediante variables de entorno (`.env`).

---

## 🏁 Cierre de Misión

Este `README.md` es un documento **vivo**. Se actualiza con cada avance significativo, no al final. La velocidad de una hackathon no es excusa para la deuda de comunicación: **el equipo que documenta mientras construye, es el equipo que demo sin fallar**.

**Vamos por el primer lugar. Data-Centric, agente por agente, commit por commit.** 💪
