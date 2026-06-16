# plugins/vlm_auditor/__init__.py
# Punto de entrada del plugin VLM Auditor para el ecosistema FiftyOne.
# FiftyOne descubre y carga este archivo automáticamente al arrancar la App.

import fiftyone.operators as foo

from .operator import VLM_Auditor_Operator


def register(plugin: foo.Plugin) -> None:
    """
    Hook de registro invocado por FiftyOne al cargar el plugin.

    Args:
        plugin: Instancia del Plugin proporcionada por el framework
                a la que se registran los operadores declarados en
                fiftyone.yml.
    """
    plugin.register(VLM_Auditor_Operator)