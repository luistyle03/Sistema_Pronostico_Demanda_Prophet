"""Hace visible la raíz del proyecto (SPD/) para todas las pruebas."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from entorno import lineas_entorno  # noqa: E402  (requiere el sys.path anterior)


def pytest_report_header() -> list[str]:
    """Anade el detalle de versiones al encabezado nativo de pytest.

    Aparece tanto en la terminal local como en el registro de integracion
    continua, de modo que cada resultado queda asociado a las versiones exactas
    con las que se obtuvo.
    """
    return ["", "entorno de ejecucion:", *[f"  {linea}" for linea in lineas_entorno()], ""]
