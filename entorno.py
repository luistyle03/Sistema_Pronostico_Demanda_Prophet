"""Constancia del entorno de ejecucion (reproducibilidad).

Reune en un solo lugar la version del interprete, de las librerias que
sustentan los cinco modelos de pronostico y la huella SHA-256 del archivo
uv.lock que produjo el entorno.

Se usa desde tres puntos:
  * pruebas/conftest.py   -> encabezado de cada corrida de pytest
  * herramientas y guiones -> encabezado en la salida de terminal
  * linea de comandos      -> `uv run python entorno.py`

No forma parte de la arquitectura hexagonal: es utileria de trazabilidad,
por eso reside en la raiz junto a verificar_integridad.py y no en src/.
"""

from __future__ import annotations

import hashlib
import pathlib
import platform
import sys
from importlib.metadata import PackageNotFoundError, version

RAIZ = pathlib.Path(__file__).resolve().parent

# Distribuciones cuya version se deja registrada. El nombre es el de PyPI,
# que no siempre coincide con el del modulo (scikit-learn -> sklearn).
PAQUETES: tuple[str, ...] = (
    "prophet",
    "statsmodels",
    "scikit-learn",
    "scipy",
    "numpy",
    "pandas",
    "flask",
    "holidays",
    "openpyxl",
    "tabulate",
    "pytest",
    "ruff",
)


def version_de(paquete: str) -> str:
    """Devuelve la version instalada sin importar el paquete.

    Se consultan los metadatos de la distribucion, no el modulo. Esto evita
    el costo de importar prophet o statsmodels solo para leer un numero.
    """
    try:
        return version(paquete)
    except PackageNotFoundError:
        return "NO INSTALADO"


def huella_lock() -> str:
    """SHA-256 de uv.lock: identifica de forma univoca la resolucion usada."""
    archivo = RAIZ / "uv.lock"
    if not archivo.is_file():
        return "uv.lock ausente"
    return hashlib.sha256(archivo.read_bytes()).hexdigest()


def resumen_entorno() -> dict[str, str]:
    """Entorno completo como diccionario, apto para exportar a Excel o JSON."""
    datos = {
        "python": platform.python_version(),
        "implementacion": platform.python_implementation(),
        "sistema": f"{platform.system()} {platform.machine()}",
    }
    datos.update({paquete: version_de(paquete) for paquete in PAQUETES})
    datos["uv.lock (sha256)"] = huella_lock()
    return datos


def lineas_entorno() -> list[str]:
    """Resumen como lista de lineas alineadas, listo para imprimir."""
    datos = resumen_entorno()
    ancho = max(len(clave) for clave in datos)
    return [f"{clave.ljust(ancho)} : {valor}" for clave, valor in datos.items()]


def imprimir_entorno(titulo: str = "ENTORNO DE EJECUCION") -> None:
    """Imprime el bloque de constancia en la salida estandar."""
    print("=" * 72)
    print(titulo)
    print("=" * 72)
    for linea in lineas_entorno():
        print("  " + linea)
    print("=" * 72)


if __name__ == "__main__":
    imprimir_entorno()
    sys.exit(0)
