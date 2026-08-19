# -*- mode: python ; coding: utf-8 -*-
"""
SPD.spec — Receta de PyInstaller para construir el ejecutable de doble clic.

USO (desde la raíz del proyecto, EN WINDOWS, dentro del entorno virtual):
    pyinstaller empaquetado/SPD.spec

Produce la carpeta dist/SPD/ con SPD.exe dentro. Ver
empaquetado/INSTRUCCIONES_EMPAQUETADO.md para el paso a paso completo.
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

# Prophet, cmdstanpy y holidays cargan archivos de datos (modelos Stan
# compilados, calendarios de feriados) que PyInstaller no detecta solo:
# collect_all arrastra módulos + binarios + datos de cada paquete.
datas, binaries, hiddenimports = [], [], []
for paquete in ("prophet", "cmdstanpy", "holidays"):
    d, b, h = collect_all(paquete)
    datas += d
    binaries += b
    hiddenimports += h

# entorno.py lee las versiones desde los metadatos de cada distribución
# (carpetas .dist-info). PyInstaller no las incluye por defecto, así que sin
# esto el ejecutable mostraría "no instalado" en toda la tabla de versiones.
for paquete in (
    "flask",
    "holidays",
    "numpy",
    "openpyxl",
    "pandas",
    "prophet",
    "scikit-learn",
    "scipy",
    "statsmodels",
):
    datas += copy_metadata(paquete)

# statsmodels y sklearn usan importaciones dinámicas internas.
hiddenimports += collect_submodules("statsmodels")
hiddenimports += collect_submodules("sklearn")

# La carpeta web (templates + static con plotly.min.js) viaja dentro del
# ejecutable y el servidor la encuentra vía sys._MEIPASS (ver servidor.py).
datas += [
    ("../src/infraestructura/web/templates", "web/templates"),
    ("../src/infraestructura/web/static", "web/static"),
]

a = Analysis(
    ["../run.py"],
    pathex=[".."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest"],  # No se usan: reducen peso.
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # Modo ONEDIR: arranque rápido y menos antivirus.
    name="SPD",
    console=True,            # La consola muestra el progreso del lote (50 series).
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="SPD",
)
