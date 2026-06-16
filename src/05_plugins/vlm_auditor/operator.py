# src/05_plugins/vlm_auditor/operator.py
# Definición del VLM_Auditor_Operator: unidad ejecutable de auditoría visual.
#
# Este operador corre dentro de la App de FiftyOne (puerto 5151) y ejecuta
# inferencia batch de VLM (gpt-4o, claude-3-5-sonnet) sobre una vista guardada,
# inyectando los resultados como fo.Classification en cada muestra.

import logging
from typing import Optional

import fiftyone as fo
import fiftyone.operators as foo
import fiftyone.operators.types as fooTypes

logger = logging.getLogger(__name__)


class VLM_Auditor_Operator(foo.Operator):
    """
    Operador delegable para auditoría visual no bloqueante del dataset.
    
    Ciclo de vida:
    1. resolve_config() — Identidad del operador en la UI
    2. resolve_input() — Formulario de entrada (selección de vista, proveedor VLM)
    3. resolve_execution_options() — Habilita ejecución delegada para lotes grandes
    4. execute() — Lógica principal de inferencia + inyección de resultados
    """

    def resolve_config(self) -> foo.OperatorConfig:
        """Registra la identidad del operador en la App."""
        return foo.OperatorConfig(
            name="vlm_auditor/vlm_auditor_operator",
            label="VLM Auditor",
            description="Ejecuta auditoría visual batch con VLMs externos",
            icon="magic",
        )

    def resolve_input(self, ctx: foo.OperatorExecutionContext) -> fooTypes.BaseView:
        """Construye el formulario de entrada en la UI."""
        inputs = fooTypes.Object()

        # Campo: Selección del proveedor VLM
        inputs.str(
            "provider",
            label="VLM Provider",
            description="Elige gpt-4o (OpenAI) o claude-3-5-sonnet (Anthropic)",
            view=fooTypes.DropdownView(
                choices=["gpt-4o", "claude-3-5-sonnet"]
            ),
            default="gpt-4o",
        )

        # Campo: Umbral de confianza mínimo
        inputs.float(
            "min_confidence",
            label="Min Confidence",
            description="Umbral de confianza mínimo [0.0 - 1.0] para verificar etiquetas",
            default=0.5,
        )

        return inputs

    def resolve_execution_options(
        self, ctx: foo.OperatorExecutionContext
    ) -> foo.ExecutionOptions:
        """Habilita ejecución delegada para evitar bloqueos en UI."""
        return foo.ExecutionOptions(
            allow_immediate_execution=True,  # Permite síncrona para lotes pequeños
            allow_delegated_execution=True,  # Habilita delegación para lotes grandes
            default_choice_to_delegated=True,  # Por defecto, delegar
        )

    def execute(
        self,
        ctx: foo.OperatorExecutionContext,
    ) -> Optional[foo.ExecutionResult]:
        """
        Lógica principal: ejecuta la auditoría VLM sobre la vista activa.
        """
        try:
            # 1. Extraiga los parámetros del formulario de la UI
            provider = ctx.params.get("provider", "gpt-4o")
            min_confidence = ctx.params.get("min_confidence", 0.5)

            # 2. Obtenga la vista activa que el usuario está viendo en la App
            view = ctx.target_view

            logger.info(
                f"[VLM_Auditor_Operator] Iniciando auditoría con {provider} (min_confidence: {min_confidence}) "
                f"sobre {len(view) if view else 0} muestras."
            )

            # 3. Importe y ejecute la lógica que ya tenemos en nuestro conector
            # Usamos importlib.import_module para evitar SyntaxError de Python por el nombre '04_agents'
            import importlib
            vlm_connector = importlib.import_module("src.04_agents.vlm_connector")
            process_view_with_vlm = vlm_connector.process_view_with_vlm
            import asyncio
            
            # Ejecutar el proceso asíncrono dentro del entorno síncrono del operador
            asyncio.run(process_view_with_vlm(view, provider, min_confidence))

            logger.info(
                f"[VLM_Auditor_Operator] Auditoría completada."
            )

            # 4. Gatille el refresco inmediato de la interfaz de usuario
            return ctx.trigger("refresh_page")

        except Exception as e:
            logger.error(
                f"[VLM_Auditor_Operator] Error durante la ejecución: {e}",
                exc_info=True,
            )
            raise
