# src/05_plugins/vlm_auditor/__init__.py
# Punto de entrada del plugin VLM Auditor para el ecosistema FiftyOne.
# 
# FLUJO DE CARGA:
# 1. El usuario ejecuta setup_plugins.py, que crea un symlink desde
#    src/05_plugins/vlm_auditor/ → ~/.fiftyone/plugins/vlm_auditor/
# 2. Al iniciar la App de FiftyOne (puerto 5151), el motor de plugins
#    descubre ~/.fiftyone/plugins/vlm_auditor/fiftyone.yml
# 3. FiftyOne importa este archivo __init__.py y llama a register(plugin)
# 4. register(plugin) registra el VLM_Auditor_Operator en la App

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
