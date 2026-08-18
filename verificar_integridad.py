"""Guarda de integridad de imports del proyecto SPD.

Comprueba de forma ESTATICA (sin ejecutar el codigo) que todo modulo `src.*`
importado por el proyecto exista realmente en el arbol versionado. Su proposito
es detectar temprano el caso mas silencioso de todos: un archivo que existe en
la maquina de desarrollo pero que nunca se agrego al repositorio.

Distingue TRES situaciones, porque exigen acciones distintas:

  1. MODULO AUSENTE — no hay ni archivo .py ni carpeta. El import fallaria con
     ModuleNotFoundError. Si esta declarado en PENDIENTES se informa y se
     tolera; si no, es un error.

  2. PAQUETE SIN __init__.py — la carpeta existe y contiene modulos, pero le
     falta el __init__.py. Python 3 SI puede importarlo (paquete de espacio de
     nombres, PEP 420), asi que el codigo funciona; pero este proyecto usa
     paquetes regulares, de modo que la ausencia significa casi siempre un
     archivo sin versionar. Se reporta como error, con el detalle exacto.

  3. TODO EN ORDEN.

Los modulos aun no implementados se declaran en PENDIENTES junto con la
iteracion en que llegan. Eso convierte la deuda planificada en algo explicito
y auditable, en lugar de un fallo silencioso.
"""

from __future__ import annotations

import ast
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent

EXCLUIDAS = {".venv", "venv", "build", "dist", "__pycache__", ".git"}

# Modulos planificados que TODAVIA no se implementan, con la iteracion en que
# llegan. Retirar de esta lista a medida que se creen: el script avisa si
# alguno ya existe, para que la lista no quede desactualizada.
PENDIENTES: dict[str, str] = {
    #"src.infraestructura.persistencia": "S14",
    #"src.infraestructura.persistencia.lector_archivos": "S14",
    "src.infraestructura.persistencia.exportador_excel": "S15",
    "src.infraestructura.web": "S15",
    "src.infraestructura.web.servidor": "S15",
}


def nombres_publicos(modulo_init: pathlib.Path) -> set[str]:
    """Nombres definidos en el nivel superior de un __init__.py."""
    if not modulo_init.is_file():
        return set()
    nombres: set[str] = set()
    arbol = ast.parse(modulo_init.read_text(encoding="utf-8"), filename=str(modulo_init))
    for nodo in arbol.body:
        if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            nombres.add(nodo.name)
        elif isinstance(nodo, ast.Assign):
            nombres.update(d.id for d in nodo.targets if isinstance(d, ast.Name))
        elif isinstance(nodo, ast.Import | ast.ImportFrom):
            nombres.update(a.asname or a.name.split(".")[0] for a in nodo.names)
    return nombres


def modulos_importados() -> set[str]:
    """Devuelve todos los modulos `src.*` a los que el proyecto hace referencia.

    Incluye tanto `import src.a.b` y `from src.a.b import X` como el caso
    `from src.a import b`, donde `b` puede ser un SUBMODULO: si `src/a/b.py` no
    existe y `b` tampoco esta definido en `src/a/__init__.py`, la referencia
    apunta a un archivo que deberia existir y no esta.
    """
    encontrados: set[str] = set()
    for archivo in sorted(RAIZ.rglob("*.py")):
        if EXCLUIDAS & set(archivo.parts) or archivo.samefile(__file__):
            continue
        arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom) and nodo.module:
                if nodo.module.split(".")[0] != "src":
                    continue
                encontrados.add(nodo.module)
                carpeta = RAIZ.joinpath(*nodo.module.split("."))
                if carpeta.is_dir():
                    definidos = nombres_publicos(carpeta / "__init__.py")
                    for alias in nodo.names:
                        if alias.name != "*" and alias.name not in definidos:
                            encontrados.add(f"{nodo.module}.{alias.name}")
            elif isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    if alias.name.split(".")[0] == "src":
                        encontrados.add(alias.name)
    return encontrados


def clasificar(modulo: str) -> str:
    """Clasifica un modulo en 'ok', 'sin_init' o 'ausente'.

    Se replica el criterio del propio interprete: un modulo se resuelve si
    existe `ruta/modulo.py`, o `ruta/modulo/__init__.py`, o —desde PEP 420— la
    carpeta `ruta/modulo/` aunque no tenga __init__.py. Ese ultimo caso se
    marca aparte porque el proyecto usa paquetes regulares.
    """
    base = RAIZ.joinpath(*modulo.split("."))
    if base.with_suffix(".py").is_file():
        return "ok"
    if (base / "__init__.py").is_file():
        return "ok"
    if base.is_dir() and any(base.glob("*.py")):
        return "sin_init"
    return "ausente"


def main() -> int:
    estados = {modulo: clasificar(modulo) for modulo in modulos_importados()}
    ausentes = sorted(m for m, e in estados.items() if e == "ausente")
    sin_init = sorted(m for m, e in estados.items() if e == "sin_init")
    inesperados = [m for m in ausentes if m not in PENDIENTES]
    resueltos = sorted(m for m in PENDIENTES if clasificar(m) == "ok")

    for modulo in ausentes:
        if modulo in PENDIENTES:
            print(f"  pendiente ({PENDIENTES[modulo]}): {modulo}")

    problemas = False

    if resueltos:
        print("\nYA IMPLEMENTADOS: retirar de PENDIENTES en verificar_integridad.py")
        for modulo in resueltos:
            print(f"  - {modulo}")
        problemas = True

    if inesperados:
        print("\nMODULOS AUSENTES NO PLANIFICADOS (probablemente sin versionar):")
        for modulo in inesperados:
            ruta = pathlib.Path(*modulo.split("."))
            print(f"  - {modulo}   -> falta {ruta}.py o {ruta}/")
        problemas = True

    if sin_init:
        print("\nPAQUETES SIN __init__.py (la carpeta existe, el archivo no):")
        for modulo in sin_init:
            ruta = pathlib.Path(*modulo.split(".")) / "__init__.py"
            print(f"  - {modulo}   -> falta {ruta}")
        print(
            "\n  Python los importaria igual (PEP 420), pero este proyecto usa\n"
            "  paquetes regulares: lo habitual es que el archivo exista en local\n"
            "  y no se haya agregado al repositorio. Verifique con:\n"
            "      git status --short\n"
            "      git ls-files src | findstr __init__"
        )
        problemas = True

    if problemas:
        return 1

    print("\nIntegridad de imports: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())