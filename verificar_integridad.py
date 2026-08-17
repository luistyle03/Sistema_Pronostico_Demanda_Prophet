"""Guarda de integridad de imports (S11).

Comprueba de forma ESTATICA (sin ejecutar el codigo) que todo modulo
`src.*` importado por el proyecto exista como archivo versionado.

Los modulos aun no implementados se declaran en PENDIENTES, junto con el
sprint en que deben existir. Esto convierte la deuda tecnica en algo
explicito y auditable en lugar de un fallo silencioso.
"""

from __future__ import annotations

import ast
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent

# Modulos planificados que TODAVIA no se implementan. Retirar de esta lista
# a medida que se creen; el script avisa si alguno ya existe.
PENDIENTES: dict[str, str] = {
    "src.aplicacion.casos_uso.evaluar_modelos": "S13",
    "src.infraestructura.estadistica.adaptador_scipy": "S13",
    "src.infraestructura.persistencia.exportador_excel": "S13",
    "src.infraestructura.persistencia.lector_archivos": "S13",
}


def modulos_importados() -> set[str]:
    encontrados: set[str] = set()
    for archivo in sorted(RAIZ.rglob("*.py")):
        if ".venv" in archivo.parts or archivo.name == pathlib.Path(__file__).name:
            continue
        arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom) and nodo.module:
                if nodo.module.split(".")[0] == "src":
                    encontrados.add(nodo.module)
            elif isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    if alias.name.split(".")[0] == "src":
                        encontrados.add(alias.name)
    return encontrados


def existe(modulo: str) -> bool:
    base = RAIZ.joinpath(*modulo.split("."))
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


def main() -> int:
    faltantes = sorted(m for m in modulos_importados() if not existe(m))
    inesperados = [m for m in faltantes if m not in PENDIENTES]
    resueltos = sorted(m for m in PENDIENTES if existe(m))

    for modulo in faltantes:
        if modulo in PENDIENTES:
            print(f"  pendiente ({PENDIENTES[modulo]}): {modulo}")

    if resueltos:
        print("\nYA IMPLEMENTADOS: retirar de PENDIENTES en verificar_integridad.py")
        for modulo in resueltos:
            print(f"  - {modulo}")
        return 1

    if inesperados:
        print("\nMODULOS FALTANTES NO PLANIFICADOS (probablemente sin versionar):")
        for modulo in inesperados:
            print(f"  - {modulo}")
        return 1

    print("\nIntegridad de imports: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
