"""
SPD — Constancia del entorno de ejecución (trazabilidad y reproducibilidad).

Reúne en un solo lugar la versión del intérprete, la de cada librería que
sustenta los cinco modelos de pronóstico y la huella SHA-256 del archivo
uv.lock que produjo el entorno. Ese hash identifica de forma unívoca la
resolución completa de dependencias, incluidas las transitivas.

Se consume desde cinco puntos, de modo que el bloque se escribe una sola vez
y aparece en toda salida de terminal del sistema:

    run.py                      -> al arrancar la aplicación web
    pruebas/conftest.py         -> encabezado de cada corrida de pytest
    pruebas/prueba_rapida.py    -> encabezado de la prueba de humo
    herramientas/*.py           -> encabezado de cada script de consola
    línea de comandos           -> uv run python entorno.py

No forma parte de la arquitectura hexagonal: es utilería de trazabilidad, sin
dependencias del dominio ni de la aplicación. Por eso reside en la raíz junto
a run.py y no dentro de src/.
"""

from __future__ import annotations

import hashlib
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# Distribuciones cuya versión se deja registrada, en orden de relevancia para
# la tesis. El nombre es el de PyPI, que no siempre coincide con el del módulo
# que se importa (scikit-learn se importa como sklearn).
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
    "pytest",
    "ruff",
)


def version_de(paquete: str) -> str:
    """Devuelve la versión instalada SIN importar el paquete.

    Se consultan los metadatos de la distribución (carpeta .dist-info), no el
    atributo __version__ del módulo. Esto evita el costo de importar prophet o
    statsmodels solo para leer un número —serían varios segundos en cada
    corrida de pytest— y funciona también con paquetes que no exponen
    __version__.
    """
    try:
        return version(paquete)
    except PackageNotFoundError:
        return "no instalado"


def huella_lock() -> str:
    """SHA-256 de uv.lock: identifica de forma unívoca la resolución usada.

    Si dos ejecuciones muestran el mismo hash, el entorno era idéntico hasta
    la última dependencia transitiva. Dentro del ejecutable empaquetado el
    archivo no viaja, y se informa como ausente.
    """
    archivo = RAIZ / "uv.lock"
    if not archivo.is_file():
        return "no disponible (ejecución empaquetada)"
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
    """Resumen como lista de líneas alineadas, lista para imprimir."""
    datos = resumen_entorno()
    ancho = max(len(clave) for clave in datos)
    return [f"{clave.ljust(ancho)} : {valor}" for clave, valor in datos.items()]


def imprimir_entorno(titulo: str = "ENTORNO DE EJECUCION") -> None:
    """Imprime el bloque de constancia en la salida estándar."""
    print("=" * 72)
    print(f"  {titulo}")
    print("=" * 72)
    for linea in lineas_entorno():
        print("  " + linea)
    print("=" * 72)
    print()


if __name__ == "__main__":
    imprimir_entorno()
    sys.exit(0)
