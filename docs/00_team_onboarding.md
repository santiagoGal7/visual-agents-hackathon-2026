# 🧭 docs/00_team_onboarding.md — Manual de Combate por Roles y Ruta de Aprendizaje

### Hackathon Voxel51 | Equipo: Visual Agent Squad 🚀

---

¡Bienvenido al campo de batalla! 🔥 Este documento es tu **mapa de guerra personal**. No es una lectura opcional ni un "léelo si tienes tiempo": es literalmente el contrato que define qué parte del repositorio dominas, qué conceptos no puedes fallar bajo presión, y cómo te autoevalúas antes de que el reloj de la hackathon empiece a correr.

Léelo una vez completo. Después, solo vuelve a tu sección de rol y conviértete en la persona más peligrosa del equipo en esa área. 💪

Regresar a: [`README.md`](../README.md)

---

## 1. Filosofía de Combate en Equipo

En una hackathon, el enemigo no es el otro equipo: es el **tiempo**. Y la forma en que un equipo pequeño le gana al tiempo no es que todos sepan un poco de todo, sino que **cada persona sea brutalmente buena en una sola cosa** y confíe ciegamente en que sus compañeros dominan la suya.

Por eso este repositorio está particionado por roles, y cada rol tiene su propia carpeta dentro de `src/` y su propio documento en `docs/`. Esto no es burocracia — es **velocidad de decisión**. Bajo presión, nadie debe preguntarse "¿esto es mío o de otro?". Si toca datos crudos, es del Dev 1. Si toca embeddings o curación inteligente, es del Dev 2. Si toca la API REST hacia el exterior, es del Dev 3. Si toca el cerebro del agente VLM o los plugins de la App, es de Santiago.

La especialización por roles es nuestra mayor ventaja competitiva por tres razones concretas:

1. **Paralelismo real, no aparente.** Cuatro personas trabajando en cuatro capas distintas del sistema (ingesta, curación, agentes, API) pueden avanzar simultáneamente sin bloquearse entre sí, porque las interfaces entre capas ya están pensadas de antemano.
2. **Responsabilidad sin ambigüedad.** Cuando algo falla en producción durante la demo, el dueño de esa parcela de código ya sabe que es su bug. No hay "yo pensé que tú lo estabas viendo".
3. **Profundidad sobre amplitud.** En 48 horas no hay tiempo de que todos se vuelvan expertos en todo. Hay tiempo de que cada uno se vuelva *letal* en su parcela y confíe en que las demás piezas del rompecabezas están en buenas manos.

> 🎯 **Regla de oro:** Tu carpeta en `src/` es tu territorio. Tu documento en `docs/` es tu biblia. Domínalos antes del día del evento, no durante.

---

## 2. Desglose Operativo de Roles (Foco, Estudio y Acción)

### 📊 Rol 1: Ingeniero de Datos e Ingesta (Dev 1)

| Categoría | Detalle |
|---|---|
| **Tu Foco en la Hackathon** | Ser el primero en tocar los datos cuando los jueces los liberen. Tu misión es limpiar, cargar y estructurar el dataset antes que nadie lo necesite para nada más. Si tú fallas, todo el equipo se queda esperando. |
| **Qué debes estudiar del repositorio** | [`docs/02_core_fiftyone.md`](./02_core_fiftyone.md) y el código de `src/02_core/ingest_data.py`. |
| **Conceptos Clave a Dominar** | La diferencia entre `Dataset` (la colección persistente completa) y `DatasetView` (una consulta filtrada y no destructiva sobre esa colección); expresiones lógicas con `fo.ViewField` (alias `F`) para construir filtros declarativos; e inyección correcta de etiquetas estructuradas usando `fo.Detections` y `fo.Segmentation`. |
| **⚡ Micro-Desafío de Entrenamiento** | Toma 5 imágenes cualesquiera de internet, colócalas en una carpeta temporal y escribe un script que las cargue a FiftyOne con el nombre `dataset-prueba`, asignándoles un tag automático llamado `mock_data`. Verifica que aparezcan correctamente en la App. |

**¿Por qué este foco importa de verdad?** Todo el pipeline —desde el VLM hasta la API REST— depende de que el dataset esté bien estructurado desde el primer segundo. Un campo mal tipado o una `View` mal construida en la hora 1 se convierte en un bug imposible de rastrear en la hora 30. Tú eres la base de la pirámide.

---

### 🧠 Rol 2: Especialista en Visión y FiftyOne Brain (Dev 2)

| Categoría | Detalle |
|---|---|
| **Tu Foco en la Hackathon** | Encontrar oro y anomalías en los datos sin tener que mirarlos uno por uno a ojo. Serás el auditor inteligente del equipo: el que detecta lo que un humano tardaría horas en notar. |
| **Qué debes estudiar del repositorio** | [`docs/03_brain_curation.md`](./03_brain_curation.md) y los scripts dentro de `src/03_brain/`. |
| **Conceptos Clave a Dominar** | Generación de embeddings con CLIP; proyecciones espaciales de alta dimensión a 2D/3D con UMAP para visualización; cálculo de `Mistakenness` para detectar posibles errores de etiquetado de los propios jueces; y búsquedas semánticas por texto sobre el espacio de embeddings. |
| **⚡ Micro-Desafío de Entrenamiento** | Lanza el script `compute_embeddings.py` sobre el `dataset-prueba` que generó el Dev 1. Abre la interfaz gráfica de FiftyOne, activa el panel de Embeddings, y encuentra visualmente qué imágenes están duplicadas o agrupadas semánticamente entre sí. |

**¿Por qué este foco importa de verdad?** El Brain es lo que convierte un dataset "plano" en un dataset *inteligente*. Si encuentras duplicados, outliers o errores de etiquetado antes que los jueces, el equipo gana puntos de calidad de datos que casi ningún otro equipo va a mostrar.

---

### 🔌 Rol 3: Desarrollador de Integración y API REST (Dev 3)

| Categoría | Detalle |
|---|---|
| **Tu Foco en la Hackathon** | Conectar el cerebro de la IA con el mundo exterior. Crearás el puente para que todo lo que el equipo construye internamente sea consumible desde fuera —por un frontend, por un juez, por un script externo. |
| **Qué debes estudiar del repositorio** | [`docs/06_production_api.md`](./06_production_api.md) y el código de `src/06_api/app.py`. |
| **Conceptos Clave a Dominar** | Gestión del ciclo de vida de FastAPI mediante `lifespan` (para inicializar y cerrar recursos costosos de forma correcta); validación de requests con Pydantic v2; y ejecución de procesos pesados de forma no bloqueante usando `BackgroundTasks`. |
| **⚡ Micro-Desafío de Entrenamiento** | Levanta el servidor local de FastAPI en el puerto `8000`. Usa Postman o un comando `curl` desde tu terminal para consultar el endpoint `/health` y el endpoint `/api/v1/dataset/summary`. Asegúrate de que ambos respondan en menos de 100 ms. |

**¿Por qué este foco importa de verdad?** Una demo brillante que solo funciona "en el notebook de un desarrollador" no convence a un jurado. Tu API es la prueba tangible de que el sistema es real, está desplegado, y responde rápido bajo presión en vivo.

---

### 🤖 Rol 4: Líder de Agentes y Extensibilidad (Santiago — Tú)

| Categoría | Detalle |
|---|---|
| **Tu Foco en la Hackathon** | Orquestar el razonamiento multimodal del Visual Agent y los componentes de extensibilidad de la UI. Tú eres quien le da "ojos pensantes" al sistema y quien lo conecta con agentes externos. |
| **Qué debes estudiar del repositorio** | [`docs/04_agent_architecture.md`](./04_agent_architecture.md), [`docs/05_mcp_plugins.md`](./05_mcp_plugins.md), y las carpetas `src/04_agents/` y `src/05_plugins/`. |
| **Conceptos Clave a Dominar** | Diseño de prompts estructurados que fuerzan salida JSON nativa en VLMs (OpenAI y Anthropic); control asíncrono de *rate limits* mediante semáforos (`asyncio.Semaphore`); y creación de `fo.Operator` personalizados que se integran como botones interactivos en la interfaz web de FiftyOne. |
| **⚡ Micro-Desafío de Entrenamiento** | Ejecuta el script `setup_plugins.py` para instalar el plugin del equipo en tu sistema local. Abre la App de FiftyOne y verifica que el botón interactivo **"VLM Auditor"** aparezca en la barra de herramientas superior, y que al hacer clic despliegue el formulario con el dropdown de selección de proveedor (GPT-4o / Claude). |

**¿Por qué este foco importa de verdad?** Esta capa es la que hace que el proyecto se sienta "agéntico" y no solo "un dataset bonito". Es también la capa más visualmente impactante en una demo en vivo: un botón que un juez puede presionar y ver razonar a un modelo de visión sobre sus propios datos, en tiempo real, vale más que cualquier slide.

---

## 3. La Estrategia del "Survival Checklist" para el Día del Evento

Va a haber bugs. Va a haber pánico. Va a haber alguien gritando "¡no carga la App!" a las 3 a.m. Cuando eso pase, **no improvisen** — corran este checklist en orden, en silencio, sin discutir, antes de tocar una sola línea de código:

1. **Activar el entorno virtual.** El 80% de los "no funciona nada" son en realidad "estoy usando el Python equivocado".
2. **Correr `verify_env.py`.** Este script existe exactamente para este momento: confirma que las dependencias, las versiones y las variables de entorno están sanas antes de que pierdas tiempo depurando síntomas en vez de causas.
3. **Revisar los logs de Mongo.** FiftyOne depende de MongoDB para persistir datasets; si Mongo no está corriendo o está corrupto, todo lo demás falla en cascada aunque el error parezca venir de otro lado.
4. **No rompan los puertos estándar.** `8000` (API REST), `5151` (FiftyOne App), `27017` (MongoDB). Si alguien más levantó un proceso en uno de esos puertos por accidente, mátenlo antes de intentar relanzar el servicio correcto.
5. **Confirmar las API Keys en el `.env`.** `OPENAI_API_KEY` y `ANTHROPIC_API_KEY` son las primeras víctimas de un copy-paste mal hecho o un archivo `.env` que no se cargó. Sin esto, el agente del Rol 4 simplemente no responde, y parecerá un bug más grave de lo que realmente es.

> 🧯 **Mentalidad de pánico controlado:** Cuando algo se rompe, el equipo entero respira, alguien corre este checklist completo en menos de 2 minutos, y solo después se empieza a debuggear el síntoma específico. El pánico sin proceso es lo que realmente pierde hackathons — no los bugs.

---

## Cierre

Cuatro roles, cuatro territorios, un solo objetivo. Si cada uno domina su sección de este documento y su carpeta correspondiente en `src/`, el equipo no está improvisando el día del evento — está **ejecutando un plan que ya practicó**.

Ahora ve a tu sección, abre tu documento técnico correspondiente, y empieza a dominar tu terreno. 🏆

Regresar a: [`README.md`](../README.md)
