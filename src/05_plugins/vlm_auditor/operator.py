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
            "vlm_provider",
            label="VLM Provider",
            description="Elige gpt-4o (OpenAI) o claude-3-5-sonnet (Anthropic)",
            view=fooTypes.DropdownView(
                choices=["gpt-4o", "claude-3-5-sonnet"]
            ),
            default="gpt-4o",
        )

        # Campo: Prompt personalizado para la auditoría
        inputs.str(
            "audit_prompt",
            label="Audit Prompt",
            description="Prompt personalizado para el VLM (ej. 'Describe los objetos presentes')",
            default="Describe los objetos y anomalías visuales presentes en esta imagen.",
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
        
        Este método es invocado bien de forma síncrona (para lotes ≤ 10 samples)
        o delegada (para lotes > 10 samples), según la configuración en
        resolve_execution_options() y la decisión del usuario en la UI.
        
        Args:
            ctx: Contexto de ejecución que proporciona acceso a:
                 - ctx.dataset: El Dataset actual
                 - ctx.view: La DatasetView filtrada (samples seleccionados)
                 - ctx.params: Los inputs del formulario del usuario
        """
        try:
            # Obtener parámetros del usuario
            vlm_provider = ctx.params.get("vlm_provider", "gpt-4o")
            audit_prompt = ctx.params.get("audit_prompt", "")

            dataset: fo.Dataset = ctx.dataset
            view: fo.DatasetView = ctx.view

            logger.info(
                f"[VLM_Auditor_Operator] Iniciando auditoría con {vlm_provider} "
                f"sobre {len(view)} muestras."
            )

            # --- Placeholder: Lógica de inferencia VLM ---
            # Esta sección será reemplazada con la lógica real del Módulo 04
            # (integración con gpt-4o / claude-3-5-sonnet, parsing de respuestas,
            # manejo de rate limits, etc.)
            
            for i, sample in enumerate(view):
                # Simular inferencia (será reemplazado con llamada real a VLM)
                ctx.set_progress(i + 1, len(view), "Auditing...")
                
                # Placeholder: inyectar una Classification genérica
                sample["vlm_audit"] = fo.Classification(
                    label="pending_audit",
                    confidence=0.0,
                    metadata={"provider": vlm_provider, "prompt": audit_prompt},
                )
                sample.save()

            logger.info(
                f"[VLM_Auditor_Operator] Auditoría completada. "
                f"{len(view)} muestras procesadas."
            )

            return foo.ExecutionResult(
                output={
                    "processed_samples": len(view),
                    "provider": vlm_provider,
                    "status": "completed",
                }
            )

        except Exception as e:
            logger.error(
                f"[VLM_Auditor_Operator] Error durante la ejecución: {e}",
                exc_info=True,
            )
            raise
