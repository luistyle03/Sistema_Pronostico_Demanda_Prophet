"""Configuracion comun de las pruebas.

Hace visible la raiz del proyecto (SPD/) para todas las pruebas y deja
constancia del entorno de ejecucion en el encabezado de cada corrida.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from entorno import lineas_entorno  # noqa: E402  (requiere el sys.path de arriba)


def pytest_report_header() -> list[str]:
    """Anade el detalle de versiones al encabezado de pytest.

    Aparece tanto en la terminal local como en el registro de GitHub
    Actions, de modo que cada ejecucion queda asociada a las versiones
    exactas con las que se obtuvieron los resultados.
    """
    return ["", "entorno de ejecucion:", *[f"  {ln}" for ln in lineas_entorno()], ""]
