# 🔌 docs/05_mcp_plugins.md — Extensibilidad: Plugins, Operators y Protocolo MCP

> **Módulo 05 — Nivel: Principal Engineer / Core Maintainer**
> Parte del repositorio de preparación para la **Hackathon de Data Agents & Visual Agents (Junio 19, 2026)**.
> Este documento es la guía definitiva de extensibilidad del sistema. Cubre la arquitectura completa de Plugins y Operators de FiftyOne, la integración del pipeline VLM/Brain directamente en la App UI, y la exposición del estado del dataset a través del Model Context Protocol (MCP) para interoperabilidad con agentes externos.

---

## Tabla de Contenidos

1. [Filosofía de Extensibilidad en FiftyOne: Operators e Interfaces](#1-filosofía-de-extensibilidad-en-fiftyone-operators-e-interfaces)
2. [Anatomía Estricta de un Operator Multimodal Personalizado (Python)](#2-anatomía-estricta-de-un-operator-multimodal-personalizado-python)
3. [Arquitectura de Archivos y Empaquetado del Plugin](#3-arquitectura-de-archivos-y-empaquetado-del-plugin)
4. [Integración Avanzada con Model Context Protocol (MCP)](#4-integración-avanzada-con-model-context-protocol-mcp)

---

## 1. Filosofía de Extensibilidad en FiftyOne: Operators e Interfaces

### 1.1 El Motor de Plugins de FiftyOne: Visión Arquitectónica

FiftyOne expone un sistema de plugins basado en el concepto de **Operators**, que son unidades de lógica de negocio ejecutables que se integran directamente en la interfaz web de la App (`localhost:5151`). Este sistema no es un add-on superficial: es el mecanismo primario a través del cual la App delega la ejecución de lógica Python arbitraria —incluyendo inferencia de modelos, auditoría de embeddings y escritura de metadatos en el dataset— a procesos del servidor, manteniendo la separación de responsabilidades entre el frontend React y el backend Python.

Desde la perspectiva de arquitectura de software, el motor de Plugins de FiftyOne implementa el patrón **Command + Strategy** combinado con un sistema de descubrimiento dinámico basado en convenciones de directorio. Cada Plugin es un paquete Python autodeclarado que el runtime de FiftyOne carga en caliente sin necesidad de reiniciar la App, siempre y cuando siga la estructura canónica bajo `~/fiftyone/plugins/`.

### 1.2 ¿Qué es un `fo.Operator`?

Un `fo.Operator` es una clase Python que hereda de `fiftyone.operators.Operator` y actúa como la unidad de extensión atómica del sistema. Define tres responsabilidades ortogonales mediante métodos que el runtime llama en secuencia durante el ciclo de vida de una acción de usuario:

| Método | Responsabilidad | Cuándo se llama |
|---|---|---|
| `resolve_config()` | Declarar la identidad del operador (nombre, etiqueta UI, icono) | En tiempo de registro y descubrimiento |
| `resolve_input()` | Construir el formulario de entrada dinámico de la UI | Cuando el usuario activa el operador en la App |
| `execute()` | Ejecutar la lógica de negocio central con los inputs del usuario | Cuando el usuario confirma el formulario |

La App web utiliza el nombre del operador retornado por `resolve_config()` como clave primaria para el registro en su tabla interna de operadores. Esta clave debe ser globalmente única dentro del contexto de los plugins instalados, y por convención sigue el esquema `plugin_name/operator_name` para prevenir colisiones entre plugins de terceros.

### 1.3 Registro y Descubrimiento en Caliente

El mecanismo de auto-descubrimiento de FiftyOne sigue estos pasos en el arranque y en cada ciclo de reload:

**Paso 1 — Escaneo del directorio base:**
El runtime escanea recursivamente el directorio `~/fiftyone/plugins/`. Cualquier subdirectorio que contenga un archivo `fiftyone.yml` es candidato a ser cargado como plugin.

**Paso 2 — Validación del manifiesto YAML:**
El archivo `fiftyone.yml` debe declarar explícitamente los operadores que el plugin expone. Si la declaración es inválida o falta, el plugin es ignorado sin lanzar excepción (falla silenciosa), lo cual es una trampa crítica durante desarrollo.

**Paso 3 — Importación del módulo Python:**
FiftyOne importa el archivo `__init__.py` (o el módulo especificado en `fiftyone.yml`) del plugin. Es en este punto donde deben ejecutarse las llamadas a `foo.register_operator(MyOperator)` para que los operadores queden registrados en el registro global del servidor.

**Paso 4 — Exposición a la App React:**
La App consume los operadores registrados vía una API REST interna. El panel de operadores (accesible con el atajo de teclado `` ` `` o desde el menú de acciones) interroga este endpoint para renderizar los botones de acción disponibles.

**Recarga en caliente (Hot Reload):**
Durante desarrollo, FiftyOne monitorea los archivos del plugin y recarga el módulo cuando detecta cambios. Este comportamiento se puede forzar manualmente llamando a `fo.reload_plugins()` desde una sesión Python activa. No requiere reiniciar ni el servidor de FiftyOne ni la sesión de Python que mantiene el dataset en memoria.

### 1.4 Diferencia Arquitectónica Crítica: Ejecución Síncrona vs. Delegada (Delegated Operators)

Esta distinción es **la decisión de diseño más importante** para el contexto de una hackathon, donde el tiempo de respuesta de la UI y la estabilidad del sistema son críticos.

#### Ejecución Síncrona (Síncrona/Inmediata)

En la ejecución por defecto, el método `execute()` del operador corre **en el mismo proceso y thread** del servidor de FiftyOne (o en un thread pool manejado por el servidor, dependiendo de la implementación del loop de eventos). Esto implica:

- **Bloqueo de la UI:** Si `execute()` tarda más de ~2-3 segundos, la interfaz de la App se congela visualmente para el usuario. Esto es inaceptable para operaciones de inferencia VLM que pueden tardar 15-60 segundos por lote.
- **Sin tolerancia a fallos:** Una excepción no capturada en `execute()` puede crashear el contexto de la sesión activa.
- **Caso de uso apropiado:** Operaciones de filtrado en memoria (< 1 segundo), actualización de metadatos de un solo sample, o lectura de estadísticas del dataset. Son exactamente las operaciones del Módulo 02 (Core).

#### Ejecución Delegada (Delegated Operators)

Los **Delegated Operators** resuelven el problema de operaciones de larga duración. Su mecanismo es fundamentalmente diferente:

1. Cuando el usuario confirma el formulario, la App no llama a `execute()` directamente.
2. En su lugar, serializa los inputs del formulario y encola una **solicitud de ejecución** en una cola de tareas (por defecto backed por MongoDB, el mismo motor que usamos en el Módulo 01).
3. Un proceso separado, el **Delegated Operator Executor** (iniciado con `fiftyone delegated launch`), consume la cola y ejecuta `execute()` de forma asíncrona.
4. El progreso se reporta a la UI a través de callbacks de `ctx.set_progress()` sin bloquear el hilo principal.

Para habilitarlo, el operador debe declararse como delegable retornando `True` desde el método `resolve_execution_options()`:

```python
def resolve_execution_options(self, ctx):
    return fo.ExecutionOptions(
        allow_immediate_execution=True,   # Permite ejecución síncrona si el lote es pequeño
        allow_delegated_execution=True,   # Habilita la cola para lotes grandes
        default_choice_to_delegated=True  # Por defecto, siempre delegar
    )
```

**Decisión de diseño para la Hackathon:**
El operador `VLM_Auditor_Operator` que construimos en la Sección 2 implementa **ejecución delegada** como comportamiento predeterminado cuando el lote supera los 10 samples. Para lotes pequeños (demos en vivo, ≤ 10 samples), permite ejecución síncrona para maximizar el impacto visual en tiempo real durante la presentación del proyecto.

---

## 2. Anatomía Estricta de un Operator Multimodal Personalizado (Python)

El siguiente script es el archivo central del plugin. Cada decisión de diseño está justificada inline. Este archivo se ubicará en `~/fiftyone/plugins/vlm_auditor/vlm_auditor_operator.py`.

```python
# =============================================================================
# FILE: ~/fiftyone/plugins/vlm_auditor/vlm_auditor_operator.py
#
# PROPÓSITO: Define el Operator VLM_Auditor_Operator que integra el pipeline
#            asíncrono de VLM (Módulo 04) y la auditoría Brain (Módulo 03)
#            directamente en la interfaz web de FiftyOne App.
#
# DEPENDENCIAS EXTERNAS:
#   - fiftyone >= 0.24.0 (requerido para la API estable de Operators v2)
#   - fiftyone.operators (submódulo del SDK de FiftyOne)
#   - asyncio (stdlib Python 3.11)
#   - La función process_view_with_vlm() del Módulo 04 debe ser importable
#     desde el path del proyecto. Asegúrese de que el PYTHONPATH esté
#     configurado correctamente en el entorno de ejecución del plugin.
#
# AUTOR: Equipo Data Agents & Visual Agents — Hackathon Junio 2026
# =============================================================================

# --- Importaciones del SDK de FiftyOne ---
# `fiftyone` es el namespace principal; `fo` es el alias canónico.
import fiftyone as fo

# `fiftyone.operators` expone la clase base Operator y el submódulo `types`
# que contiene los tipos de componentes de UI (Choices, Number, String, etc.)
import fiftyone.operators as foo
import fiftyone.operators.types as types

# --- Importaciones de la stdlib ---
import asyncio   # Para ejecutar el coroutine asíncrono del Módulo 04 desde contexto síncrono
import logging   # Logging estructurado; no usar print() en código de producción

# --- Importación del pipeline VLM del Módulo 04 ---
# NOTA CRÍTICA: Esta importación asume que el directorio raíz del proyecto
# está en el PYTHONPATH. En caso de ejecutar en modo delegado con el executor
# de FiftyOne, este path debe ser configurado en el archivo .env del entorno
# o en el fiftyone.yml bajo la clave `pythonpath`.
#
# La función `process_view_with_vlm` es el corazón del Módulo 04:
# acepta una `fo.DatasetView`, un string de proveedor VLM y un umbral de
# confianza, y escribe los resultados como `fo.Classification` en cada sample.
try:
    from src.agent.vlm_pipeline import process_view_with_vlm
except ImportError as e:
    # Fallo graceful: el operador queda registrado pero execute() fallará
    # con un mensaje de error informativo en lugar de crashear la App.
    logging.error(
        "[VLM_Auditor_Operator] No se pudo importar el pipeline VLM del Módulo 04. "
        "Verifique que PYTHONPATH incluya el directorio raíz del proyecto. "
        f"Error original: {e}"
    )
    # Definimos un stub para que la clase pueda ser instanciada sin ImportError
    async def process_view_with_vlm(view, provider, confidence_threshold):
        raise RuntimeError(
            "El módulo VLM no está disponible. "
            "Verifique la configuración de PYTHONPATH."
        )

# Configuración del logger para este módulo.
# Usamos el namespace completo para facilitar el filtrado en entornos de logging centralizado.
logger = logging.getLogger("hackathon.plugins.vlm_auditor")


# =============================================================================
# CLASE PRINCIPAL: VLM_Auditor_Operator
# =============================================================================

class VLM_Auditor_Operator(foo.Operator):
    """
    Operator de FiftyOne que integra el pipeline multimodal de VLM del Módulo 04
    y la auditoría de embeddings del Módulo 03 directamente en la interfaz web
    de FiftyOne App.

    CICLO DE VIDA DE UNA EJECUCIÓN:
    1. El usuario abre el panel de operadores en la App (tecla ` o menú de acciones).
    2. La App renderiza el botón "🤖 VLM Auditor" usando los metadatos de resolve_config().
    3. Al hacer clic, la App invoca resolve_input() y renderiza el formulario dinámico.
    4. El usuario selecciona el proveedor VLM y el umbral de confianza, y confirma.
    5. La App invoca execute() con el contexto completo (ctx), que contiene:
       - ctx.target_view: la DatasetView activa visible en la UI en ese momento.
       - ctx.params: el diccionario de inputs del formulario.
       - ctx.dataset: referencia al dataset completo.
    6. execute() delega al pipeline asíncrono del Módulo 04.
    7. Al completar, se dispara un trigger de refresco de la UI.
    """

    # =========================================================================
    # MÉTODO: resolve_config
    # =========================================================================

    @property
    def config(self):
        """
        Declaración de la identidad del operador en el sistema de plugins.

        CONTRATO:
        - `name`: Identificador único en snake_case. Sigue el esquema
          `plugin_name/operator_name` para prevenir colisiones de namespace.
          CRÍTICO: Este nombre es la clave primaria con la que la App registra
          el operador. Un cambio en este valor después del despliegue requiere
          limpiar el caché de plugins de FiftyOne.

        - `label`: Texto visible en el botón de la UI. Debe ser autoexplicativo
          y orientado a la acción. Máximo ~30 caracteres para evitar truncamiento
          en la UI según el breakpoint del panel de operadores.

        - `icon`: Path relativo al ícono SVG dentro del directorio del plugin,
          o una URL absoluta. FiftyOne renderiza este ícono junto al label.
          Si el archivo no existe, la App usa un ícono genérico de plugin sin error.

        - `description`: Texto de ayuda contextual mostrado en el tooltip del botón.
          Debe describir el efecto secundario del operador (qué escribe en el dataset)
          para que el usuario pueda tomar una decisión informada antes de ejecutar.

        - `dynamic`: Si es True, la App llamará a resolve_input() cada vez que
          el usuario modifique un campo del formulario, permitiendo formularios
          con lógica condicional (ej. mostrar opciones adicionales según el
          proveedor VLM seleccionado).
        """
        return foo.OperatorConfig(
            # Nombre único global del operador. Prefijado con el nombre del plugin
            # para evitar colisiones con operadores de otros plugins instalados.
            name="vlm_auditor/audit_view_with_vlm",

            # Etiqueta visible en el panel de operadores de la App.
            # El emoji provee un identificador visual inmediato durante demos en vivo.
            label="🤖 VLM Auditor",

            # Ícono SVG personalizado. El path es relativo al directorio raíz del plugin.
            # Ver Sección 3 para la estructura de archivos del plugin.
            icon="/icons/vlm_auditor_icon.svg",

            # Descripción completa para el tooltip de la UI.
            description=(
                "Procesa la vista activa del dataset con un modelo VLM (GPT-4o o "
                "Claude 3.5 Sonnet) para enriquecer cada sample con etiquetas "
                "sugeridas, puntuación de confianza y detección de errores de "
                "etiquetado. Los resultados se persisten en el campo 'vlm_audit' "
                "de cada sample como fo.Classification."
            ),

            # dynamic=True habilita formularios con lógica reactiva.
            # En este operador lo usamos para mostrar un aviso de costo
            # estimado según el número de samples en la vista activa.
            dynamic=True,
        )

    # =========================================================================
    # MÉTODO: resolve_input
    # =========================================================================

    def resolve_input(self, ctx):
        """
        Construye dinámicamente el formulario de entrada de la UI.

        Este método es invocado por la App cada vez que el usuario abre
        el operador y, si dynamic=True, cada vez que modifica un campo.
        Debe ser idempotente y de ejecución rápida (< 100ms) ya que bloquea
        el render del formulario en la UI.

        PARÁMETRO ctx (ExecutionContext):
        - ctx.params: dict con los valores actuales del formulario (útil en
          formularios dinámicos para leer el valor de un campo ya seleccionado
          y condicionar la renderización de otros campos).
        - ctx.dataset: el dataset completo actualmente cargado en la sesión.
        - ctx.target_view: la DatasetView activa en la UI al momento de
          invocar el operador.
        - ctx.view: alias de ctx.target_view en versiones recientes del SDK.

        RETORNA: Un objeto `types.Property` que la App usa para renderizar
        el formulario completo.

        NOTA SOBRE types.Object vs types.Property:
        `types.Object` es el tipo compuesto (equivalente a un struct o schema
        de formulario). `types.Property` es el wrapper que le asigna
        metadatos de UI (label, descripción, required). Siempre se retorna
        un `types.Property` que envuelve un `types.Object`.
        """

        # `inputs` es el objeto raíz del formulario. Actuará como un contenedor
        # de campos de primer nivel.
        inputs = types.Object()

        # -----------------------------------------------------------------
        # CAMPO 1: Dropdown para selección del proveedor VLM
        # -----------------------------------------------------------------
        # `types.Choices` es el tipo de dato para selectores tipo dropdown.
        # Cada opción se añade con .add_choice(value, label=..., description=...).
        # El campo `value` es lo que se recibirá en ctx.params["vlm_provider"].
        vlm_provider_choices = types.Choices()

        vlm_provider_choices.add_choice(
            # value: identificador interno de la opción. Debe ser un string
            # sin espacios, ya que se mapea directamente al argumento `provider`
            # de la función process_view_with_vlm() del Módulo 04.
            "gpt-4o",
            # label: texto visible en el dropdown de la UI.
            label="GPT-4o (OpenAI)",
            # description: texto secundario de ayuda visible bajo la opción.
            description="Modelo multimodal de OpenAI. Costo estimado: ~$0.01/imagen. "
                        "Requiere OPENAI_API_KEY en el entorno.",
        )

        vlm_provider_choices.add_choice(
            "claude-3-5-sonnet",
            label="Claude 3.5 Sonnet (Anthropic)",
            description="Modelo multimodal de Anthropic con alta capacidad de razonamiento. "
                        "Costo estimado: ~$0.008/imagen. Requiere ANTHROPIC_API_KEY en el entorno.",
        )

        # Agregamos el campo dropdown al objeto de inputs.
        # `types.Dropdown` es el componente de UI que renderiza las Choices.
        # `required=True` fuerza al usuario a hacer una selección antes de confirmar.
        inputs.enum(
            # Nombre del campo. Es la clave en ctx.params con la que se accederá
            # al valor seleccionado dentro de execute().
            "vlm_provider",
            # Lista de valores válidos (se deriva automáticamente de vlm_provider_choices).
            vlm_provider_choices.values(),
            # Tipo de selector de UI.
            view=types.Dropdown(
                label="Proveedor VLM",
                description="Seleccione el modelo de visión-lenguaje para el análisis.",
                choices=vlm_provider_choices,
            ),
            required=True,
            default="gpt-4o",
        )

        # -----------------------------------------------------------------
        # CAMPO 2: Campo numérico para el umbral de confianza
        # -----------------------------------------------------------------
        # Solo los samples cuyo campo `confidence` (del Módulo 04) sea MENOR
        # al umbral serán marcados como `potential_mistake=True` en el
        # resultado de la auditoría.
        inputs.float(
            # Nombre del campo. Accesible en execute() como ctx.params["confidence_threshold"].
            "confidence_threshold",
            # Tipo de componente de UI para inputs numéricos flotantes.
            view=types.FieldView(
                label="Umbral de Confianza",
                description=(
                    "Samples con confianza VLM por debajo de este valor "
                    "serán marcados como potenciales errores de etiquetado. "
                    "Rango recomendado: 0.60 – 0.85."
                ),
            ),
            # min/max definen la validación de rango en el lado del cliente (UI).
            # Valores fuera de rango muestran un error en el formulario sin
            # llegar a invocar execute().
            min=0.0,
            max=1.0,
            default=0.75,
            required=True,
        )

        # -----------------------------------------------------------------
        # BLOQUE DINÁMICO: Advertencia de costo estimado
        # -----------------------------------------------------------------
        # Aprovechamos dynamic=True para calcular y mostrar el número de
        # samples en la vista activa actual, permitiendo al usuario estimar
        # el costo y tiempo de ejecución antes de confirmar.
        #
        # `ctx.target_view` puede ser None si no hay vista activa (dataset completo).
        # Usamos la lógica defensiva habitual del repositorio.
        try:
            if ctx.target_view is not None:
                # Obtener el número de samples en la vista activa.
                # `.count()` ejecuta una agregación eficiente en MongoDB
                # sin cargar los samples en memoria.
                num_samples = ctx.target_view.count()
                view_description = f"Vista activa: {num_samples} sample(s) seleccionado(s)."
            else:
                num_samples = ctx.dataset.count()
                view_description = (
                    f"Sin vista activa. Se procesará el dataset completo: "
                    f"{num_samples} sample(s)."
                )

            # Alertar si la vista activa supera los 50 samples para recomendar
            # la ejecución delegada. El usuario no puede forzar esto desde la UI
            # (lo gestiona resolve_execution_options), pero el aviso mejora la UX.
            if num_samples > 50:
                view_description += (
                    f" ⚠️ Para lotes > 50 samples, la ejecución será automáticamente "
                    f"delegada al executor de background para no bloquear la UI."
                )

            # Agregamos un campo de tipo Notice (solo lectura) para mostrar
            # información contextual sin requerir input del usuario.
            inputs.message(
                "view_info",
                label="Información de la Vista Activa",
                description=view_description,
            )

        except Exception as e:
            # Si falla la inspección de la vista (edge case: vista corrupta,
            # dataset no inicializado), logueamos y continuamos sin el notice.
            logger.warning(
                "[VLM_Auditor_Operator.resolve_input] No se pudo inspeccionar "
                f"la vista activa para el aviso de costo: {e}"
            )

        # Retornamos el schema completo del formulario envuelto en un Property.
        # `view=types.View(label=...)` define el título del panel del formulario en la UI.
        return types.Property(inputs, view=types.View(label="Configuración de Auditoría VLM"))

    # =========================================================================
    # MÉTODO: resolve_execution_options
    # =========================================================================

    def resolve_execution_options(self, ctx):
        """
        Define la estrategia de ejecución del operador según el tamaño del lote.

        LÓGICA DE DECISIÓN:
        - Lotes pequeños (≤ 10 samples): ejecución síncrona/inmediata.
          Ideal para demos en vivo donde el impacto visual instantáneo
          es más importante que la robustez.
        - Lotes medianos/grandes (> 10 samples): delegación automática
          al executor de background via la cola de MongoDB.
          Previene el bloqueo de la UI y permite monitorear el progreso.

        Este método NO es un método abstracto de la clase base, por lo tanto
        no es obligatorio implementarlo. Si se omite, FiftyOne asume
        ejecución síncrona pura (allow_immediate_execution=True,
        allow_delegated_execution=False).
        """
        try:
            # Determinamos el tamaño del lote para la decisión de estrategia.
            if ctx.target_view is not None:
                num_samples = ctx.target_view.count()
            else:
                num_samples = ctx.dataset.count()

            # Para lotes pequeños, permitimos ejecución inmediata como default
            # y también ejecución delegada como opción disponible en la UI.
            if num_samples <= 10:
                return foo.ExecutionOptions(
                    allow_immediate_execution=True,
                    allow_delegated_execution=True,
                    # default_choice_to_delegated=False: por defecto, ejecución inmediata
                    # para máximo impacto visual en demos.
                    default_choice_to_delegated=False,
                )
            else:
                # Para lotes grandes, forzamos la delegación automáticamente.
                return foo.ExecutionOptions(
                    allow_immediate_execution=False,  # Bloqueamos la ejecución síncrona
                    allow_delegated_execution=True,
                    default_choice_to_delegated=True,
                )

        except Exception as e:
            # Si no podemos determinar el tamaño, vamos con el modo seguro (delegado).
            logger.warning(
                "[VLM_Auditor_Operator.resolve_execution_options] "
                f"Fallback a ejecución delegada por error al inspeccionar vista: {e}"
            )
            return foo.ExecutionOptions(
                allow_immediate_execution=False,
                allow_delegated_execution=True,
                default_choice_to_delegated=True,
            )

    # =========================================================================
    # MÉTODO: execute
    # =========================================================================

    def execute(self, ctx):
        """
        Motor de acción central del operador. Ejecuta el pipeline VLM sobre
        la vista activa y refresca la UI al completar.

        PARÁMETRO ctx (ExecutionContext):
        - ctx.params (dict): Contiene los valores del formulario con exactamente
          las mismas claves definidas en resolve_input():
            - ctx.params["vlm_provider"] (str): "gpt-4o" o "claude-3-5-sonnet"
            - ctx.params["confidence_threshold"] (float): valor entre 0.0 y 1.0

        - ctx.target_view (fo.DatasetView | None): La vista activa en la UI en el
          momento en que el usuario confirmó el formulario. Si el usuario tiene
          una selección de samples activa (ej. dibujó un polígono en el embedding
          space del UMAP del Módulo 03), este será el subconjunto seleccionado.
          Si no hay vista activa, es equivalente al dataset completo.

        - ctx.dataset (fo.Dataset): El dataset completo. Útil para operaciones
          que necesitan contexto global (ej. calcular estadísticas de todo el
          dataset para normalizar scores de la vista activa).

        FLUJO DE EJECUCIÓN:
        1. Extracción y validación defensiva de parámetros del formulario.
        2. Resolución de la vista objetivo (target_view o dataset completo).
        3. Llamada a process_view_with_vlm() del Módulo 04 usando asyncio.
        4. Reporte de progreso y conteo de samples procesados.
        5. Trigger de refresco visual de la App.

        RETORNA: dict con los triggers de UI a ejecutar por la App.
        La clave estándar es el resultado de ctx.trigger() para acciones de UI.
        """

        # -----------------------------------------------------------------
        # PASO 1: Extracción y validación defensiva de parámetros
        # -----------------------------------------------------------------
        # Extraemos con .get() y default values para prevenir KeyError.
        # Esto es especialmente importante si el operador es invocado
        # programáticamente (ej. en tests o desde otro operador) sin
        # pasar todos los params del formulario.
        vlm_provider = ctx.params.get("vlm_provider", "gpt-4o")
        confidence_threshold = ctx.params.get("confidence_threshold", 0.75)

        # Validación de tipo y rango para confidence_threshold.
        # El validador de la UI previene la mayoría de los casos inválidos,
        # pero execute() puede ser llamado directamente en contextos de testing.
        try:
            confidence_threshold = float(confidence_threshold)
            if not (0.0 <= confidence_threshold <= 1.0):
                raise ValueError(
                    f"confidence_threshold debe estar en [0.0, 1.0], "
                    f"recibido: {confidence_threshold}"
                )
        except (TypeError, ValueError) as e:
            logger.error(
                f"[VLM_Auditor_Operator.execute] Parámetro inválido: {e}. "
                f"Usando valor por defecto 0.75."
            )
            confidence_threshold = 0.75

        # Validación del proveedor VLM contra la lista de valores permitidos.
        ALLOWED_PROVIDERS = {"gpt-4o", "claude-3-5-sonnet"}
        if vlm_provider not in ALLOWED_PROVIDERS:
            logger.error(
                f"[VLM_Auditor_Operator.execute] Proveedor VLM desconocido: "
                f"'{vlm_provider}'. Usando 'gpt-4o' como fallback."
            )
            vlm_provider = "gpt-4o"

        logger.info(
            f"[VLM_Auditor_Operator.execute] Iniciando auditoría. "
            f"Proveedor: {vlm_provider}, Umbral: {confidence_threshold}"
        )

        # -----------------------------------------------------------------
        # PASO 2: Resolución de la vista objetivo
        # -----------------------------------------------------------------
        # `ctx.target_view` es la vista activa en la UI cuando el usuario
        # confirmó el formulario. Puede ser:
        # - Una DatasetView con filtros activos (ej. solo imágenes de una clase).
        # - Una DatasetView de samples seleccionados en el mapa UMAP del Módulo 03.
        # - None si no hay ninguna vista activa (se procesa el dataset completo).
        #
        # DECISIÓN DE DISEÑO: Siempre preferir target_view sobre el dataset
        # completo, para que el operador respete el contexto visual del usuario.
        if ctx.target_view is not None:
            target_view = ctx.target_view
            num_samples = target_view.count()
            logger.info(
                f"[VLM_Auditor_Operator.execute] Procesando vista activa con "
                f"{num_samples} sample(s)."
            )
        else:
            # Si no hay vista activa, procesamos el dataset completo.
            # Creamos una vista identity (sin filtros) del dataset para mantener
            # la interfaz uniforme con process_view_with_vlm() que espera una
            # DatasetView, no un Dataset.
            target_view = ctx.dataset.view()
            num_samples = target_view.count()
            logger.info(
                f"[VLM_Auditor_Operator.execute] Sin vista activa. "
                f"Procesando dataset completo: {num_samples} sample(s)."
            )

        # Guard clause: si la vista está vacía, abortamos con mensaje informativo.
        if num_samples == 0:
            logger.warning(
                "[VLM_Auditor_Operator.execute] La vista objetivo está vacía. "
                "No hay samples para procesar. Abortando."
            )
            # Retornamos un trigger de notificación al usuario en la UI.
            return ctx.trigger(
                "show_output",
                params={
                    "outputs": {"message": "⚠️ La vista activa está vacía. Seleccione samples antes de ejecutar."},
                    "results": {},
                },
            )

        # -----------------------------------------------------------------
        # PASO 3: Llamada al pipeline asíncrono del Módulo 04
        # -----------------------------------------------------------------
        # process_view_with_vlm() es una coroutine asíncrona (async def).
        # execute() de FiftyOne Operator es síncrono (no async def), por lo
        # tanto necesitamos un bridge entre el mundo síncrono y asíncrono.
        #
        # ESTRATEGIA: asyncio.run() crea un nuevo event loop, ejecuta el
        # coroutine hasta su completitud, y retorna el resultado.
        #
        # ADVERTENCIA: asyncio.run() NO puede ser llamado si ya existe un
        # event loop corriendo en el thread actual (ej. en entornos Jupyter
        # o si el servidor de FiftyOne usa uvloop). En ese caso, usar:
        #   loop = asyncio.get_event_loop()
        #   loop.run_until_complete(process_view_with_vlm(...))
        # o alternativamente la librería `nest_asyncio` para anidar loops.
        #
        # En el contexto de este plugin (ejecutado por el servidor de FiftyOne
        # en un worker thread separado), asyncio.run() es la solución correcta.
        try:
            # Reporte de progreso inicial a la UI (visible en modo delegado).
            ctx.set_progress(0.0, label=f"Iniciando pipeline VLM para {num_samples} samples...")

            # Ejecución del coroutine asíncrono del Módulo 04.
            # process_view_with_vlm() es responsable de:
            # 1. Iterar sobre los samples de la vista.
            # 2. Codificar cada imagen en Base64.
            # 3. Invocar la API del VLM con control de Rate Limits (asyncio.Semaphore).
            # 4. Parsear el JSON de respuesta (campos: suggested_tags, confidence,
            #    potential_mistake, rationale).
            # 5. Escribir los resultados como fo.Classification en sample["vlm_audit"].
            # 6. Llamar a sample.save() para persistir en MongoDB.
            results = asyncio.run(
                process_view_with_vlm(
                    view=target_view,
                    provider=vlm_provider,
                    confidence_threshold=confidence_threshold,
                )
            )

            # Reporte de progreso final.
            ctx.set_progress(1.0, label="Pipeline VLM completado.")

            logger.info(
                f"[VLM_Auditor_Operator.execute] Pipeline completado exitosamente. "
                f"Resultados: {results}"
            )

        except RuntimeError as e:
            # Capturamos RuntimeError específicamente para el caso donde
            # process_view_with_vlm no está disponible (stub del ImportError inicial).
            logger.error(
                f"[VLM_Auditor_Operator.execute] Error de configuración del módulo VLM: {e}"
            )
            return ctx.trigger(
                "show_output",
                params={
                    "outputs": {
                        "message": f"❌ Error de configuración: {str(e)}"
                    },
                    "results": {},
                },
            )
        except Exception as e:
            # Captura genérica para errores del pipeline (timeout de API,
            # JSON inválido, error de MongoDB, etc.).
            logger.exception(
                f"[VLM_Auditor_Operator.execute] Error inesperado durante "
                f"la ejecución del pipeline VLM: {e}"
            )
            return ctx.trigger(
                "show_output",
                params={
                    "outputs": {
                        "message": (
                            f"❌ Error durante la ejecución del pipeline VLM: {str(e)}. "
                            f"Revise los logs del servidor para más detalles."
                        )
                    },
                    "results": {},
                },
            )

        # -----------------------------------------------------------------
        # PASO 4: Trigger de refresco visual de la App
        # -----------------------------------------------------------------
        # `ctx.trigger("refresh_page")` instruye a la App React a recargar
        # el estado del dataset desde el servidor, actualizando:
        # - Los valores de los campos en el panel de muestra (Sample Panel).
        # - Las etiquetas renderizadas sobre las imágenes en la vista de grid.
        # - Los contadores de la barra lateral (si hay filtros activos).
        # - El mapa de embeddings del Módulo 03 (si está visible), con los
        #   nuevos colores derivados del campo vlm_audit.confidence.
        #
        # ALTERNATIVA MÁS FINA: ctx.trigger("set_view", params={...}) permite
        # no solo refrescar sino también cambiar la vista activa programáticamente,
        # por ejemplo, para mostrar automáticamente solo los samples con
        # potential_mistake=True después de la auditoría.
        return ctx.trigger("refresh_page")


# =============================================================================
# REGISTRO DEL OPERADOR
# =============================================================================
# Esta llamada es el punto de entrada que FiftyOne ejecuta al importar el módulo.
# Sin esta línea, la clase VLM_Auditor_Operator existe en Python pero no está
# disponible en la App (no aparece en el panel de operadores).
#
# CRÍTICO: `foo.register_operator` debe ser llamado en el scope de módulo
# (no dentro de funciones ni clases), para garantizar que se ejecute
# durante la fase de importación del plugin por el runtime de FiftyOne.

def register(plugin):
    """
    Función de registro del plugin.

    FiftyOne llama automáticamente a esta función cuando carga el plugin,
    pasando la instancia del plugin como argumento. Los operadores deben
    ser registrados aquí usando plugin.register().

    NOTA: En versiones recientes del SDK (>= 0.24), el patrón recomendado
    es la función `register(plugin)` en lugar de llamadas directas a
    `foo.register_operator()`. Ambos patrones son compatibles, pero
    `register(plugin)` es más robusto para la gestión de dependencias
    entre operadores del mismo plugin.
    """
    plugin.register(VLM_Auditor_Operator)
    logger.info(
        "[vlm_auditor plugin] VLM_Auditor_Operator registrado exitosamente "
        "en el registro de operadores de FiftyOne."
    )
```

---

## 3. Arquitectura de Archivos y Empaquetado del Plugin

### 3.1 Árbol de Directorios Canónico

FiftyOne descubre plugins automáticamente escaneando `~/fiftyone/plugins/`. Cada subdirectorio de primer nivel es un plugin candidato. La estructura obligatoria es la siguiente:

```
~/fiftyone/plugins/
└── vlm_auditor/                          # Directorio raíz del plugin
    │                                     # El nombre de este directorio es el
    │                                     # identificador del plugin en el sistema.
    │
    ├── fiftyone.yml                      # [OBLIGATORIO] Manifiesto del plugin.
    │                                     # Sin este archivo, el directorio es ignorado.
    │                                     # Ver Sección 3.2 para el contenido completo.
    │
    ├── __init__.py                       # [OBLIGATORIO] Punto de entrada Python del plugin.
    │                                     # Debe contener o importar la función register().
    │                                     # FiftyOne importa este módulo durante la carga.
    │
    ├── vlm_auditor_operator.py           # Clase VLM_Auditor_Operator (Sección 2).
    │                                     # Importado desde __init__.py.
    │
    ├── icons/                            # [OPCIONAL] Recursos visuales del plugin.
    │   └── vlm_auditor_icon.svg          # Ícono del operador. Referenciado en resolve_config()
    │                                     # como "/icons/vlm_auditor_icon.svg".
    │                                     # Dimensiones recomendadas: 24x24px, stroke-based SVG.
    │
    ├── requirements.txt                  # [RECOMENDADO] Dependencias Python del plugin.
    │                                     # FiftyOne no las instala automáticamente,
    │                                     # pero sirven como documentación de contrato.
    │
    └── README.md                         # [RECOMENDADO] Documentación del plugin para el equipo.
```

### 3.2 Contenido del `__init__.py`

El archivo `__init__.py` es el punto de entrada que FiftyOne importa. Debe re-exportar la función `register()` del módulo principal:

```python
# ~/fiftyone/plugins/vlm_auditor/__init__.py
#
# Punto de entrada del plugin vlm_auditor.
# FiftyOne importa este módulo durante el proceso de descubrimiento y carga.
# La función `register` es el contrato de extensión del sistema de plugins.

from .vlm_auditor_operator import register

# Re-exportamos `register` explícitamente para que FiftyOne pueda encontrarla
# en el scope del módulo __init__ sin necesidad de especificar el submódulo
# en fiftyone.yml (aunque también puede especificarse allí para mayor claridad).
__all__ = ["register"]
```

### 3.3 El Manifiesto `fiftyone.yml` — Configuración Completa

El archivo `fiftyone.yml` es el contrato declarativo del plugin. FiftyOne lo lee antes de importar el código Python, lo que le permite hacer validaciones y mostrar metadatos del plugin en la UI de gestión de plugins sin necesidad de ejecutar código arbitrario.

```yaml
# ~/fiftyone/plugins/vlm_auditor/fiftyone.yml
#
# Manifiesto del Plugin VLM Auditor
# Hackathon Data Agents & Visual Agents — Junio 2026
#
# REFERENCIA DE ESQUEMA: https://docs.voxel51.com/plugins/developing_plugins.html
# VALIDACIÓN: `fiftyone plugins validate ~/fiftyone/plugins/vlm_auditor`

# ---------------------------------------------------------------------------
# SECCIÓN: Identidad del Plugin
# ---------------------------------------------------------------------------

# `name`: Identificador único del plugin en el ecosistema FiftyOne.
# Debe coincidir exactamente con el nombre del directorio del plugin.
# Convenio: kebab-case, sin espacios ni caracteres especiales.
name: vlm-auditor

# `version`: Versión del plugin siguiendo Semantic Versioning (SemVer).
# Incrementar el patch version (0.0.X) para bugfixes,
# el minor version (0.X.0) para nuevas features no breaking,
# el major version (X.0.0) para cambios breaking de API.
version: 1.0.0

# `label`: Nombre legible del plugin. Aparece en la lista de plugins de la App
# y en la documentación generada automáticamente.
label: VLM Auditor — Multimodal AI Labeling Pipeline

# `description`: Descripción extendida del plugin. Soporta Markdown básico.
# Visible en el panel de gestión de plugins de la App y en el catálogo de plugins.
description: |
  Plugin de FiftyOne que integra un pipeline de análisis multimodal basado en
  Vision-Language Models (VLMs) directamente en la App. Procesa la vista activa
  del dataset con GPT-4o o Claude 3.5 Sonnet para enriquecer cada sample con:

  - **suggested_tags**: Etiquetas semánticas generadas por el VLM.
  - **confidence**: Puntuación de confianza del modelo (0.0 – 1.0).
  - **potential_mistake**: Flag booleano de posible error de etiquetado.
  - **rationale**: Justificación textual del análisis del VLM.

  Los resultados se persisten en el campo `vlm_audit` de cada sample como
  `fo.Classification` para integración nativa con los paneles de FiftyOne.

# ---------------------------------------------------------------------------
# SECCIÓN: Autoría y Mantenimiento
# ---------------------------------------------------------------------------

authors:
  - name: Equipo Data Agents & Visual Agents
    email: team@hackathon2026.dev

# `license`: Tipo de licencia del plugin.
license: MIT

# `homepage`: URL del repositorio del proyecto.
homepage: https://github.com/hackathon-2026/data-visual-agents

# `changelog`: URL del changelog del plugin (opcional).
# changelog: https://github.com/hackathon-2026/data-visual-agents/blob/main/CHANGELOG.md

# ---------------------------------------------------------------------------
# SECCIÓN: Compatibilidad de SDK
# ---------------------------------------------------------------------------

# `fiftyone_compatibility`: Specifica el rango de versiones del SDK de FiftyOne
# con las que este plugin es compatible, usando la sintaxis de especificación
# de versiones de Python (PEP 440).
# CRÍTICO: Un rango demasiado estricto previene la instalación; demasiado amplio
# puede causar errores de runtime si se usa una API que cambió entre versiones.
fiftyone_compatibility: ">=0.24.0,<1.0.0"

# `python_compatibility`: Rango de versiones de Python soportadas.
python_compatibility: ">=3.10,<3.13"

# ---------------------------------------------------------------------------
# SECCIÓN: Declaración de Operadores
# ---------------------------------------------------------------------------
# Esta sección es el registro declarativo de todos los operadores que el plugin
# expone. FiftyOne usa esta lista para:
# 1. Mostrar los operadores disponibles en la UI antes de importar el módulo Python.
# 2. Validar que los operadores registrados en código coincidan con los declarados.
# 3. Generar la documentación del plugin automáticamente.

operators:
  # Cada entrada en la lista corresponde a un operador.
  - name: audit_view_with_vlm
    # `name`: DEBE coincidir exactamente con el valor retornado por
    # OperatorConfig.name en resolve_config(), excluyendo el prefijo del plugin.
    # El nombre completo en la App será: "vlm-auditor/audit_view_with_vlm".

    label: "🤖 VLM Auditor"
    # `label`: Texto visible en el panel de operadores. Debe coincidir
    # con el label en OperatorConfig para consistencia.

    description: >
      Procesa la vista activa del dataset con GPT-4o o Claude 3.5 Sonnet
      y persiste los resultados del análisis como fo.Classification
      en el campo vlm_audit de cada sample.
    # `description`: Descripción breve del operador. Aparece en el tooltip
    # del botón en la App y en la documentación del plugin.

    icon: /icons/vlm_auditor_icon.svg
    # `icon`: Path relativo al ícono SVG del operador dentro del directorio
    # del plugin. El path es relativo a la raíz del plugin (donde está fiftyone.yml).

    execute_as_generator: false
    # `execute_as_generator`: Si es true, execute() es un generador (yield)
    # que permite streaming de resultados parciales a la UI. False para
    # el patrón estándar de retorno único.

    unlisted: false
    # `unlisted`: Si es true, el operador no aparece en la lista de la UI
    # pero puede ser invocado programáticamente. Útil para operadores
    # de uso interno o sub-operadores auxiliares.

# ---------------------------------------------------------------------------
# SECCIÓN: Configuración del Módulo Python
# ---------------------------------------------------------------------------

# `py_packages`: Lista de paquetes Python requeridos por el plugin.
# FiftyOne NO los instala automáticamente; son para documentación y validación.
# Para instalación automática, considerar el uso de fiftyone plugins requirements.
py_packages:
  - "openai>=1.0.0"
  - "anthropic>=0.20.0"
  - "Pillow>=10.0.0"

# `js_bundle`: Path al bundle JavaScript del plugin (para plugins con componentes
# React personalizados). Este plugin es Python-only, por lo que se omite.
# js_bundle: dist/index.umd.js

# `server`: Si el plugin incluye un servidor Express/FastAPI embebido,
# se configura aquí. No aplica para este plugin.
# server: false
```

### 3.4 Comandos de Gestión del Plugin

```bash
# ============================================================
# INSTALACIÓN Y VERIFICACIÓN DEL PLUGIN
# ============================================================

# Verificar que el plugin es detectado correctamente por FiftyOne
# (retorna la lista de plugins instalados con su estado de validación)
fiftyone plugins list

# Validar el fiftyone.yml sin cargar el código Python
# (útil para detectar errores de sintaxis YAML antes del despliegue)
fiftyone plugins validate ~/fiftyone/plugins/vlm_auditor

# Forzar la recarga del plugin en caliente (sin reiniciar la App)
# Ejecutar desde una sesión Python activa con FiftyOne cargado:
python -c "import fiftyone as fo; fo.reload_plugins(); print('Plugins recargados.')"

# Deshabilitar temporalmente el plugin sin desinstalarlo
# (útil para debugging de conflictos entre plugins)
fiftyone plugins disable vlm-auditor

# Re-habilitar el plugin
fiftyone plugins enable vlm-auditor

# ============================================================
# EJECUCIÓN DEL DELEGATED EXECUTOR (para lotes grandes)
# ============================================================
# El executor de operadores delegados debe correr como proceso separado.
# En producción, gestionarlo con systemd o supervisor.
# En la hackathon, ejecutarlo en una terminal dedicada.

fiftyone delegated launch

# Monitorear el estado de las tareas delegadas en cola
fiftyone delegated list

# Ver logs detallados del executor (nivel DEBUG)
fiftyone delegated launch --log-level DEBUG
```

---

## 4. Integración Avanzada con Model Context Protocol (MCP)

### 4.1 Visión del Protocolo MCP en el Contexto del Proyecto

El **Model Context Protocol (MCP)** es un protocolo abierto, estandarizado por Anthropic y adoptado por la industria, que define cómo los agentes de IA y las herramientas de codificación asistida acceden a datos y ejecutan funciones de forma estructurada, trazable y reversible. En el contexto de este proyecto, MCP transforma el dataset visual de FiftyOne —que reside en MongoDB y es accesible vía el SDK Python— en un conjunto de **herramientas MCP**, haciendo que el estado actual del dataset sea directamente interrogable por:

- **Claude Code** (herramienta de coding asistido por IA de Anthropic): Permite que el agente de coding consulte el dataset en lenguaje natural ("¿cuántos samples tienen `potential_mistake=True`?") y use los resultados para escribir código de análisis contextualmente correcto.
- **Cursor** (editor de código con IA): Accede al dataset vía el servidor MCP local para autocomplete y generación de código contextualizado con el estado real de los datos.
- **Agentes autónomos personalizados**: Cualquier agente construido sobre el SDK de MCP puede usar el servidor MCP de FiftyOne como una herramienta de acceso a datos sin necesidad de conocer la API de FiftyOne.
- **La propia App de FiftyOne** (soporte nativo desde v0.24+): La App puede actuar como cliente MCP, integrando herramientas externas en el pipeline de análisis de datos.

La propuesta de valor central es la siguiente: **en lugar de que el ingeniero tenga que escribir código para responder preguntas sobre el dataset ("¿cuántos samples tienen confidence < 0.7 y etiqueta 'cat'?"), el agente de IA puede formular la pregunta en lenguaje natural y el servidor MCP la traduce a operaciones del SDK de FiftyOne en tiempo real.**

### 4.2 Arquitectura del Servidor MCP para FiftyOne

El servidor MCP de FiftyOne se implementa como un proceso Python independiente que expone funciones del SDK como herramientas MCP (`@mcp.tool()`). Se comunica con los clientes MCP (Claude Code, Cursor, agentes) a través de stdio o HTTP con SSE (Server-Sent Events), según el tipo de transporte configurado.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ARQUITECTURA MCP + FiftyOne                     │
│                                                                     │
│   ┌──────────────┐    MCP Protocol    ┌─────────────────────────┐   │
│   │  Claude Code │ ◄──────────────── │   FiftyOne MCP Server   │   │
│   │   (Cliente)  │    (stdio/SSE)    │  mcp_fiftyone_server.py  │   │
│   └──────────────┘                   └────────────┬────────────┘   │
│                                                   │                 │
│   ┌──────────────┐                                │ FiftyOne SDK    │
│   │    Cursor    │ ◄─────────────────────────────┤                 │
│   │   (Cliente)  │    MCP Protocol               │                 │
│   └──────────────┘                                ▼                 │
│                                        ┌──────────────────────┐    │
│   ┌──────────────────┐                 │  fo.Dataset (Memory) │    │
│   │  Agente Autónomo │ ◄──────────────►│  MongoDB (Port 27017)│    │
│   │    (Cliente)     │                 │  FiftyOne App :5151  │    │
│   └──────────────────┘                 └──────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.3 Implementación del Servidor MCP

El siguiente script implementa el servidor MCP completo. Utiliza la librería `mcp` de Anthropic (el SDK oficial del protocolo) para exponer las funciones más relevantes del SDK de FiftyOne como herramientas interrogables por agentes externos.

```python
# =============================================================================
# FILE: src/mcp/mcp_fiftyone_server.py
#
# PROPÓSITO: Servidor MCP que expone el estado del dataset de FiftyOne como
#            herramientas MCP accesibles por Claude Code, Cursor y agentes
#            autónomos construidos sobre el SDK de MCP.
#
# EJECUCIÓN:
#   # Modo stdio (para Claude Code y Cursor — transporte recomendado para local):
#   python src/mcp/mcp_fiftyone_server.py
#
#   # Modo SSE (para agentes HTTP — requiere especificar host y puerto):
#   python src/mcp/mcp_fiftyone_server.py --transport sse --port 8765
#
# DEPENDENCIAS:
#   pip install mcp fiftyone
#
# NOTA: El servidor debe iniciarse con el dataset ya cargado en la sesión Python,
# o con un nombre de dataset activo en la instancia local de MongoDB de FiftyOne.
# =============================================================================

import argparse
import json
import logging
from typing import Any, Optional

# SDK oficial del Model Context Protocol (Anthropic)
# Documentación: https://github.com/modelcontextprotocol/python-sdk
import mcp
import mcp.server
import mcp.server.stdio
import mcp.types as mcp_types

# SDK de FiftyOne
import fiftyone as fo
import fiftyone.core.aggregations as foag

# Configuración del logger estructurado
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("hackathon.mcp.fiftyone_server")

# =============================================================================
# CONFIGURACIÓN DEL SERVIDOR MCP
# =============================================================================

# Inicialización del servidor MCP con nombre e información de versión.
# El `name` aparece en los logs de los clientes MCP y en la descripción
# del servidor en mcp_config.json.
server = mcp.server.Server(
    name="fiftyone-dataset-server",
    version="1.0.0",
)


# =============================================================================
# HERRAMIENTA 1: get_dataset_summary
# =============================================================================

@server.tool()
async def get_dataset_summary(dataset_name: Optional[str] = None) -> mcp_types.TextContent:
    """
    Retorna un resumen completo del dataset activo de FiftyOne.

    Incluye: número total de samples, campos disponibles con sus tipos,
    distribución de etiquetas, y estadísticas de campos numéricos clave
    como vlm_audit.confidence (generado por el pipeline del Módulo 04).

    Args:
        dataset_name: Nombre del dataset a consultar. Si es None, usa el
                      dataset más recientemente cargado o el dataset por
                      defecto de la sesión activa.

    Returns:
        JSON estructurado con el resumen completo del dataset.
    """
    try:
        # Resolución del dataset a consultar.
        if dataset_name:
            if not fo.dataset_exists(dataset_name):
                return mcp_types.TextContent(
                    type="text",
                    text=json.dumps({
                        "error": f"Dataset '{dataset_name}' no encontrado.",
                        "available_datasets": fo.list_datasets(),
                    }, indent=2, ensure_ascii=False)
                )
            dataset = fo.load_dataset(dataset_name)
        else:
            # Si no se especifica nombre, lista los datasets disponibles
            # y usa el primero disponible como fallback.
            available = fo.list_datasets()
            if not available:
                return mcp_types.TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "No hay datasets disponibles en esta instancia de FiftyOne.",
                        "suggestion": "Ejecute el Módulo 01 para inicializar el dataset.",
                    }, indent=2, ensure_ascii=False)
                )
            dataset = fo.load_dataset(available[0])
            logger.info(f"[get_dataset_summary] Usando dataset por defecto: {dataset.name}")

        # Construcción del resumen.
        # Usamos agregaciones nativas de FiftyOne que se traducen a queries
        # de MongoDB eficientes (no cargan todos los samples en memoria).
        summary = {
            "dataset_name": dataset.name,
            "num_samples": len(dataset),
            "media_type": dataset.media_type,
            "persistent": dataset.persistent,
            "tags": dataset.distinct("tags"),
            "field_schema": {
                field_name: str(field)
                for field_name, field in dataset.get_field_schema().items()
            },
        }

        # Estadísticas del campo vlm_audit si existe (generado por el Módulo 04).
        if "vlm_audit" in dataset.get_field_schema():
            try:
                confidence_bounds = dataset.bounds("vlm_audit.confidence")
                potential_mistakes_count = dataset.count_values("vlm_audit.potential_mistake")
                summary["vlm_audit_stats"] = {
                    "confidence_min": confidence_bounds[0],
                    "confidence_max": confidence_bounds[1],
                    "potential_mistakes_distribution": potential_mistakes_count,
                }
            except Exception as e:
                logger.warning(f"[get_dataset_summary] No se pudieron calcular stats de vlm_audit: {e}")
                summary["vlm_audit_stats"] = {"error": str(e)}

        # Estadísticas de Ground Truth si existe el campo `ground_truth`.
        if "ground_truth" in dataset.get_field_schema():
            try:
                label_counts = dataset.count_values("ground_truth.label")
                summary["ground_truth_distribution"] = label_counts
            except Exception as e:
                logger.warning(f"[get_dataset_summary] No se pudieron calcular stats de ground_truth: {e}")

        return mcp_types.TextContent(
            type="text",
            text=json.dumps(summary, indent=2, ensure_ascii=False)
        )

    except Exception as e:
        logger.exception(f"[get_dataset_summary] Error inesperado: {e}")
        return mcp_types.TextContent(
            type="text",
            text=json.dumps({"error": str(e)}, indent=2, ensure_ascii=False)
        )


# =============================================================================
# HERRAMIENTA 2: query_samples
# =============================================================================

@server.tool()
async def query_samples(
    dataset_name: Optional[str] = None,
    label_filter: Optional[str] = None,
    min_confidence: Optional[float] = None,
    max_confidence: Optional[float] = None,
    potential_mistakes_only: bool = False,
    tags: Optional[list[str]] = None,
    limit: int = 20,
) -> mcp_types.TextContent:
    """
    Consulta samples del dataset aplicando filtros combinados.

    Implementa el patrón de consulta en memoria del Módulo 02 (Core)
    mediante fo.DatasetView encadenando .match() y .filter_labels().

    Args:
        dataset_name: Nombre del dataset. None = dataset por defecto.
        label_filter: Filtro de etiqueta de ground_truth (ej. "cat", "dog").
        min_confidence: Filtro mínimo del campo vlm_audit.confidence.
        max_confidence: Filtro máximo del campo vlm_audit.confidence.
        potential_mistakes_only: Si True, retorna solo samples marcados
                                 como potential_mistake=True por el VLM.
        tags: Lista de tags para filtrar samples (operación OR).
        limit: Número máximo de samples a retornar (max recomendado: 100).

    Returns:
        JSON con la lista de samples que cumplen los criterios de filtrado,
        incluyendo sus campos más relevantes para el análisis.
    """
    try:
        # Resolución del dataset.
        if dataset_name:
            dataset = fo.load_dataset(dataset_name)
        else:
            available = fo.list_datasets()
            if not available:
                return mcp_types.TextContent(
                    type="text",
                    text=json.dumps({"error": "No hay datasets disponibles."}, indent=2)
                )
            dataset = fo.load_dataset(available[0])

        # Construcción de la DatasetView con filtros encadenados.
        # Patrón del Módulo 02: cada .match() añade un stage de pipeline
        # a la query de MongoDB sin ejecutarla inmediatamente (lazy evaluation).
        view = dataset.view()

        # Filtro por tags (operación OR entre los tags de la lista).
        if tags:
            view = view.match_tags(tags)

        # Filtro por etiqueta de ground_truth.
        if label_filter:
            view = view.match(
                fo.ViewField("ground_truth.label") == label_filter
            )

        # Filtros sobre el campo vlm_audit (generado por el Módulo 04).
        if min_confidence is not None:
            view = view.match(
                fo.ViewField("vlm_audit.confidence") >= min_confidence
            )

        if max_confidence is not None:
            view = view.match(
                fo.ViewField("vlm_audit.confidence") <= max_confidence
            )

        if potential_mistakes_only:
            view = view.match(
                fo.ViewField("vlm_audit.potential_mistake") == True
            )

        # Aplicar límite para prevenir respuestas excesivamente grandes.
        view = view.limit(min(limit, 200))

        # Serialización de los resultados.
        # Construimos una representación JSON liviana de cada sample,
        # seleccionando solo los campos más relevantes para el agente.
        results = []
        for sample in view.select_fields([
            "id", "filepath", "tags",
            "ground_truth", "vlm_audit",
        ]):
            sample_dict = {
                "id": str(sample.id),
                "filepath": sample.filepath,
                "tags": sample.tags,
            }

            # Campos de ground_truth (pueden ser None si no están etiquetados).
            if hasattr(sample, "ground_truth") and sample.ground_truth is not None:
                sample_dict["ground_truth"] = {
                    "label": sample.ground_truth.label,
                    "confidence": sample.ground_truth.confidence,
                }
            else:
                sample_dict["ground_truth"] = None

            # Campos de vlm_audit (generados por el Módulo 04).
            if hasattr(sample, "vlm_audit") and sample.vlm_audit is not None:
                sample_dict["vlm_audit"] = {
                    "label": sample.vlm_audit.label,
                    "confidence": getattr(sample.vlm_audit, "confidence", None),
                    "potential_mistake": getattr(sample.vlm_audit, "potential_mistake", None),
                    "rationale": getattr(sample.vlm_audit, "rationale", None),
                }
            else:
                sample_dict["vlm_audit"] = None

            results.append(sample_dict)

        response = {
            "total_matching": view.count(),
            "returned": len(results),
            "filters_applied": {
                "label_filter": label_filter,
                "min_confidence": min_confidence,
                "max_confidence": max_confidence,
                "potential_mistakes_only": potential_mistakes_only,
                "tags": tags,
                "limit": limit,
            },
            "samples": results,
        }

        return mcp_types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, ensure_ascii=False)
        )

    except Exception as e:
        logger.exception(f"[query_samples] Error: {e}")
        return mcp_types.TextContent(
            type="text",
            text=json.dumps({"error": str(e)}, indent=2, ensure_ascii=False)
        )


# =============================================================================
# HERRAMIENTA 3: get_audit_statistics
# =============================================================================

@server.tool()
async def get_audit_statistics(dataset_name: Optional[str] = None) -> mcp_types.TextContent:
    """
    Retorna estadísticas detalladas de la auditoría VLM del Módulo 04.

    Incluye: distribución de confianza, tasa de errores detectados,
    concordancia entre ground_truth y vlm_audit, y los samples
    con mayor discrepancia para revisión prioritaria.

    Args:
        dataset_name: Nombre del dataset. None = dataset por defecto.

    Returns:
        JSON con estadísticas de auditoría y recomendaciones de acción.
    """
    try:
        # Resolución del dataset.
        if dataset_name:
            dataset = fo.load_dataset(dataset_name)
        else:
            available = fo.list_datasets()
            if not available:
                return mcp_types.TextContent(
                    type="text",
                    text=json.dumps({"error": "No hay datasets disponibles."}, indent=2)
                )
            dataset = fo.load_dataset(available[0])

        # Verificación de que el campo vlm_audit existe (fue generado por el Módulo 04).
        if "vlm_audit" not in dataset.get_field_schema():
            return mcp_types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "El campo 'vlm_audit' no existe en el dataset.",
                    "suggestion": (
                        "Ejecute el operador VLM_Auditor_Operator desde la App "
                        "o el pipeline del Módulo 04 directamente para generar "
                        "las anotaciones de auditoría."
                    )
                }, indent=2, ensure_ascii=False)
            )

        # Cálculo de estadísticas agregadas usando la API de agregaciones de FiftyOne.
        # Estas operaciones se ejecutan como queries de aggregation pipeline en MongoDB.
        total_samples = len(dataset)
        audited_view = dataset.match(fo.ViewField("vlm_audit").exists(True))
        num_audited = audited_view.count()

        # Estadísticas de confianza.
        confidence_bounds = audited_view.bounds("vlm_audit.confidence")
        confidence_mean = audited_view.mean("vlm_audit.confidence")

        # Distribución de potential_mistake.
        mistake_distribution = audited_view.count_values("vlm_audit.potential_mistake")
        num_potential_mistakes = mistake_distribution.get(True, 0)

        # Concordancia entre ground_truth y vlm_audit (solo si ambos existen).
        concordance_stats = {}
        if "ground_truth" in dataset.get_field_schema():
            # Samples donde ambas etiquetas coinciden.
            both_labeled = audited_view.match(
                fo.ViewField("ground_truth").exists(True)
            )
            total_both = both_labeled.count()

            if total_both > 0:
                # Concordancia: ground_truth.label == vlm_audit.label
                concordant = both_labeled.match(
                    fo.ViewField("ground_truth.label") == fo.ViewField("vlm_audit.label")
                ).count()
                concordance_rate = concordant / total_both if total_both > 0 else 0.0

                concordance_stats = {
                    "samples_with_both_labels": total_both,
                    "concordant_samples": concordant,
                    "discordant_samples": total_both - concordant,
                    "concordance_rate": round(concordance_rate, 4),
                }

        # Los 5 samples con menor confianza (candidatos prioritarios para revisión humana).
        low_confidence_samples = (
            audited_view
            .sort_by("vlm_audit.confidence", reverse=False)
            .limit(5)
            .values(["id", "filepath", "vlm_audit.confidence", "vlm_audit.potential_mistake"])
        )
        # Unpacking de los arrays paralelos retornados por .values()
        ids, filepaths, confidences, mistakes = low_confidence_samples
        priority_review = [
            {
                "id": str(sid),
                "filepath": fp,
                "confidence": conf,
                "potential_mistake": mistake,
            }
            for sid, fp, conf, mistake in zip(ids, filepaths, confidences, mistakes)
        ]

        stats = {
            "dataset_name": dataset.name,
            "total_samples": total_samples,
            "audited_samples": num_audited,
            "audit_coverage_pct": round(num_audited / total_samples * 100, 2) if total_samples > 0 else 0.0,
            "confidence_stats": {
                "min": confidence_bounds[0],
                "max": confidence_bounds[1],
                "mean": round(confidence_mean, 4) if confidence_mean else None,
            },
            "potential_mistakes": {
                "count": num_potential_mistakes,
                "rate_pct": round(num_potential_mistakes / num_audited * 100, 2) if num_audited > 0 else 0.0,
            },
            "concordance_with_ground_truth": concordance_stats,
            "priority_review_candidates": priority_review,
        }

        return mcp_types.TextContent(
            type="text",
            text=json.dumps(stats, indent=2, ensure_ascii=False)
        )

    except Exception as e:
        logger.exception(f"[get_audit_statistics] Error: {e}")
        return mcp_types.TextContent(
            type="text",
            text=json.dumps({"error": str(e)}, indent=2, ensure_ascii=False)
        )


# =============================================================================
# HERRAMIENTA 4: list_available_datasets
# =============================================================================

@server.tool()
async def list_available_datasets() -> mcp_types.TextContent:
    """
    Lista todos los datasets disponibles en la instancia local de FiftyOne/MongoDB.

    Incluye metadatos básicos de cada dataset: nombre, número de samples,
    tipo de media, y si fue persistido en MongoDB.

    Returns:
        JSON con la lista de datasets disponibles y sus metadatos.
    """
    try:
        dataset_names = fo.list_datasets()
        datasets_info = []

        for name in dataset_names:
            try:
                ds = fo.load_dataset(name)
                datasets_info.append({
                    "name": name,
                    "num_samples": len(ds),
                    "media_type": ds.media_type,
                    "persistent": ds.persistent,
                    "has_vlm_audit": "vlm_audit" in ds.get_field_schema(),
                    "has_ground_truth": "ground_truth" in ds.get_field_schema(),
                    "has_embeddings": "embedding" in ds.get_field_schema(),
                })
            except Exception as e:
                datasets_info.append({
                    "name": name,
                    "error": f"No se pudo cargar: {str(e)}",
                })

        return mcp_types.TextContent(
            type="text",
            text=json.dumps({
                "total_datasets": len(dataset_names),
                "datasets": datasets_info,
            }, indent=2, ensure_ascii=False)
        )

    except Exception as e:
        logger.exception(f"[list_available_datasets] Error: {e}")
        return mcp_types.TextContent(
            type="text",
            text=json.dumps({"error": str(e)}, indent=2, ensure_ascii=False)
        )


# =============================================================================
# PUNTO DE ENTRADA DEL SERVIDOR
# =============================================================================

async def main():
    """Inicializa y ejecuta el servidor MCP en modo stdio."""
    logger.info(
        "[FiftyOne MCP Server] Iniciando servidor MCP. "
        "Escuchando en stdio. "
        "Herramientas disponibles: get_dataset_summary, query_samples, "
        "get_audit_statistics, list_available_datasets"
    )
    # El transporte stdio es el estándar para servidores MCP locales.
    # Permite que Claude Code y Cursor lo gestionen como un subproceso.
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### 4.4 Archivo de Configuración `mcp_config.json`

El archivo `mcp_config.json` registra el servidor MCP local dentro del ecosistema de herramientas del cliente (Claude Code, Cursor, u otro agente MCP-compatible). Este archivo debe ubicarse en el directorio de configuración del cliente correspondiente.

**Para Claude Code (`~/.claude/mcp_config.json`):**

```json
{
  "$schema": "https://json.schemastore.org/mcp-config.json",
  "mcpServers": {
    "fiftyone-dataset-server": {
      "command": "python",
      "args": [
        "/ruta/absoluta/al/proyecto/src/mcp/mcp_fiftyone_server.py"
      ],
      "env": {
        "PYTHONPATH": "/ruta/absoluta/al/proyecto",
        "FIFTYONE_DATABASE_URI": "mongodb://localhost:27017",
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}"
      },
      "description": "Servidor MCP que expone el dataset visual de FiftyOne como herramientas interrogables. Permite consultar samples, estadísticas de auditoría VLM y metadatos del dataset en lenguaje natural.",
      "disabled": false,
      "alwaysAllow": [
        "list_available_datasets",
        "get_dataset_summary",
        "query_samples",
        "get_audit_statistics"
      ]
    }
  }
}
```

**Para Cursor (`.cursor/mcp.json` en el directorio raíz del proyecto):**

```json
{
  "mcpServers": {
    "fiftyone-dataset-server": {
      "command": "python",
      "args": [
        "${workspaceFolder}/src/mcp/mcp_fiftyone_server.py"
      ],
      "env": {
        "PYTHONPATH": "${workspaceFolder}",
        "FIFTYONE_DATABASE_URI": "mongodb://localhost:27017"
      }
    }
  }
}
```

**Estructura JSON completa con todos los metadatos (`config/mcp_config.json` en el repo):**

```json
{
  "$schema": "https://json.schemastore.org/mcp-config.json",
  "_comment": "Configuración MCP para el servidor FiftyOne del proyecto Hackathon 2026. Copiar a ~/.claude/mcp_config.json para Claude Code o a .cursor/mcp.json para Cursor.",
  "mcpServers": {
    "fiftyone-dataset-server": {
      "command": "python",
      "args": [
        "${PROJECT_ROOT}/src/mcp/mcp_fiftyone_server.py"
      ],
      "env": {
        "PYTHONPATH": "${PROJECT_ROOT}",
        "FIFTYONE_DATABASE_URI": "mongodb://localhost:27017",
        "FIFTYONE_DEFAULT_APP_PORT": "5151",
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
        "LOG_LEVEL": "INFO"
      },
      "description": "Servidor MCP local para el dataset visual de FiftyOne. Expone 4 herramientas: list_available_datasets, get_dataset_summary, query_samples, get_audit_statistics.",
      "version": "1.0.0",
      "author": "Equipo Data Agents & Visual Agents — Hackathon Junio 2026",
      "homepage": "https://github.com/hackathon-2026/data-visual-agents",
      "disabled": false,
      "timeout_seconds": 30,
      "alwaysAllow": [
        "list_available_datasets",
        "get_dataset_summary",
        "query_samples",
        "get_audit_statistics"
      ],
      "capabilities": {
        "tools": true,
        "resources": false,
        "prompts": false,
        "logging": true
      }
    }
  }
}
```

### 4.5 Guía de Uso del Servidor MCP con Claude Code

Una vez registrado el servidor MCP, Claude Code puede interactuar con el dataset de FiftyOne en lenguaje natural durante sesiones de codificación. A continuación, ejemplos de interacciones naturales que el servidor MCP habilita:

**Escenario 1 — Diagnóstico de la cobertura de auditoría:**
```
Desarrollador: "¿Cuántos samples del dataset han sido auditados por el VLM y cuál es la tasa de errores detectados?"

Claude Code: [Invoca get_audit_statistics()]
→ "El dataset 'hackathon_dataset' tiene 1,250 samples. El pipeline VLM ha auditado 847 (67.8%). 
   De los samples auditados, 134 (15.8%) fueron marcados como potential_mistake=True. 
   La confianza media del VLM es 0.7823. La tasa de concordancia con el ground_truth es del 89.3%."
```

**Escenario 2 — Consulta contextual para generación de código:**
```
Desarrollador: "Escríbeme el código para cargar solo los samples con etiqueta 'cat' y confianza VLM < 0.7"

Claude Code: [Invoca query_samples(label_filter="cat", max_confidence=0.7, limit=5) para validar que existen]
→ "Encontré 23 samples 'cat' con confidence < 0.7. Aquí el código FiftyOne para cargarlos:

   view = dataset.match(
       (fo.ViewField('ground_truth.label') == 'cat') &
       (fo.ViewField('vlm_audit.confidence') < 0.7)
   )
   session = fo.launch_app(view)"
```

**Escenario 3 — Revisión de candidatos prioritarios:**
```
Desarrollador: "¿Cuáles son los 5 samples con mayor probabilidad de ser errores de etiquetado?"

Claude Code: [Invoca get_audit_statistics()]
→ "Los 5 samples con menor confianza VLM (candidatos prioritarios para revisión) son:
   1. sample_id: 6a2f... | confidence: 0.312 | filepath: /data/images/cat_042.jpg
   2. sample_id: 9b1e... | confidence: 0.341 | filepath: /data/images/dog_117.jpg
   ..."
```

### 4.6 Soporte MCP Nativo de FiftyOne (v0.24+)

FiftyOne 0.24+ incluye soporte MCP nativo que expone el estado completo del servidor de la App como herramientas MCP, sin necesidad del servidor personalizado de la Sección 4.3. Para activarlo:

```python
# Activación del servidor MCP nativo de FiftyOne
import fiftyone as fo

# Cargar el dataset (Módulo 01)
dataset = fo.load_dataset("hackathon_dataset")

# Iniciar la App con el servidor MCP habilitado
# El servidor MCP nativo escucha en el puerto 5152 por defecto (configurable)
session = fo.launch_app(
    dataset,
    port=5151,          # Puerto de la App React
    # El servidor MCP nativo se inicia automáticamente en el mismo proceso
    # cuando fiftyone.config.mcp_server_enabled = True
)

# Alternativa: iniciar el servidor MCP de forma independiente
# (útil para integrarlo en el mcp_config.json sin lanzar la App visualmente)
fo.start_mcp_server(
    port=5152,          # Puerto del servidor MCP
    dataset=dataset,    # Dataset a exponer
)
```

> **Nota de compatibilidad para la Hackathon:** La disponibilidad del servidor MCP nativo de FiftyOne depende de la versión exacta instalada. Si la versión local no incluye `fo.start_mcp_server()`, el servidor personalizado de la Sección 4.3 proporciona funcionalidad equivalente y es completamente autónomo.

---

## Resumen Ejecutivo del Módulo

| Componente | Archivo | Función en el Sistema |
|---|---|---|
| `VLM_Auditor_Operator` | `vlm_auditor/vlm_auditor_operator.py` | Integra el pipeline VLM y auditoría Brain en la App UI |
| `fiftyone.yml` | `vlm_auditor/fiftyone.yml` | Manifiesto declarativo del plugin para auto-descubrimiento |
| `__init__.py` | `vlm_auditor/__init__.py` | Punto de entrada del plugin; registra el Operator |
| `mcp_fiftyone_server.py` | `src/mcp/mcp_fiftyone_server.py` | Servidor MCP que expone el dataset a agentes externos |
| `mcp_config.json` | `config/mcp_config.json` | Registro del servidor MCP para Claude Code / Cursor |

---

## Navegación

← [Módulo 04 — Arquitectura del Agente VLM](./04_agent_architecture.md)

↑ [README Principal](../README.md)

---

*Documento generado para el repositorio de la Hackathon Data Agents & Visual Agents — Junio 19, 2026.*
*Nivel de ingeniería: Principal Software Engineer / Core Maintainer Voxel51 / Arquitecto Senior MLOps.*
