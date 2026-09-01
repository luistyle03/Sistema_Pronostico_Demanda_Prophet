<!-- Estado real del proyecto: GitHub recalcula estas insignias solo -->
[![tests](https://github.com/luistyle03/Sistema_Pronostico_Demanda_Prophet/actions/workflows/test.yml/badge.svg)](https://github.com/luistyle03/Sistema_Pronostico_Demanda_Prophet/actions/workflows/tests.yml) [![release](https://img.shields.io/github/v/release/luistyle03/Sistema_Pronostico_Demanda_Prophet?display_name=tag&sort=semver)](https://github.com/luistyle03/Sistema_Pronostico_Demanda_Prophet/releases) [![license](https://img.shields.io/github/license/luistyle03/Sistema_Pronostico_Demanda_Prophet)](LICENSE) ![último commit](https://img.shields.io/github/last-commit/luistyle03/Sistema_Pronostico_Demanda_Prophet) ![tamaño del repositorio](https://img.shields.io/github/repo-size/luistyle03/Sistema_Pronostico_Demanda_Prophet) ![líneas de código](https://img.shields.io/github/languages/code-size/luistyle03/Sistema_Pronostico_Demanda_Prophet?label=código)

<!-- Leídas del pyproject.toml del propio repositorio: cambian solas al editarlo -->
![python](https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fluistyle03%2FSistema_Pronostico_Demanda_Prophet%2Fmain%2Fpyproject.toml&query=%24.project%5B%27requires-python%27%5D&label=python&logo=python&logoColor=white&color=3776AB) ![proyecto](https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fluistyle03%2FSistema_Pronostico_Demanda_Prophet%2Fmain%2Fpyproject.toml&query=%24.project.version&label=versión&color=informational)

<!-- Declaraciones de diseño: son afirmaciones del autor, no mediciones -->
![Arquitectura: Hexagonal](https://img.shields.io/badge/Arquitectura-Hexagonal-blue) ![Principios: SOLID](https://img.shields.io/badge/Principios-SOLID-yellow) ![Código: Clean Code](https://img.shields.io/badge/Código-Clean_Code-brightgreen) ![Metodología: PXP](https://img.shields.io/badge/Metodología-PXP-orange) [![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)


# SPD — Sistema de Pronóstico de Demanda

Sistema de pronóstico de demanda diaria por producto para micro y pequeñas empresas del
sector retail, basado en el algoritmo Prophet y entregado como aplicación de ejecución
local. Código de la tesis de Pedro Alberto Luis Méndez (UTP, Ingeniería de Sistemas).

Licencia MIT.

## Requisitos

Solo [uv](https://docs.astral.sh/uv/). No hace falta instalar Python a mano: uv descarga
la versión exacta que exige `.python-version` (3.14.6).

## Reproducir el entorno

```bash
uv sync --locked          # reproduce uv.lock; aborta si no corresponde al pyproject
uv run python entorno.py  # versiones exactas y huella SHA-256 del bloqueo
```

## Ejecutar la aplicación

```bash
uv run python run.py      # abre http://127.0.0.1:8765
```

## Reproducir el experimento de la tesis

El dataset **no se distribuye** en este repositorio: los términos de la competencia
Corporación Favorita de Kaggle restringen su redistribución. Descargue `train.csv` desde
Kaggle y colóquelo donde prefiera.

```bash
# 1) Muestra principal: 50 series de demanda continua
uv run python herramientas/preparar_favorita.py "RUTA/train.csv" --modo series \
    --tiendas 10 --productos-por-tienda 5 --semilla 42 \
    --min-promedio-diario 30 --max-prop-ceros 0.15 --salida favorita_50_series.csv

# 2) Experimento principal: ficha de registro con las métricas por serie y modelo
uv run python herramientas/evaluar_modelos_cli.py favorita_50_series.csv \
    --fraccion-prueba 0.20 --salida resultados_evaluacion.xlsx

# 3) Contraste confirmatorio de HE1 a HE5 (unica fuente estadistica del estudio)
uv run python herramientas/contraste_hipotesis.py favorita_50_series.csv \
    --fraccion-prueba 0.2 --salida contraste.xlsx

# 4) Estabilidad: 10 muestras x 3 particiones = 30 configuraciones
uv run python herramientas/experimento_factorial.py "RUTA/train.csv" \
    --semillas 101 102 103 104 105 106 107 108 109 110 --salida factorial.xlsx

# 5) Verificacion del instrumento de medicion
uv run python herramientas/validacion_instrumento.py
```

## Comprobaciones

```bash
uv run python -m pytest pruebas -v      # 32 pruebas
uv run ruff check .                     # estilo
uv run black --check .                  # formato
uv run python verificar_integridad.py   # modulos importados vs versionados
```

## Qué NO hace el software

La hipótesis específica HE7 —idoneidad operativa— **no la calcula este programa**. Es un
análisis documental que el investigador diligencia sobre la matriz del Instrumento B,
citando la fuente de cada calificación. El software solo aporta los tiempos medidos como
insumo empírico de uno de los siete criterios.

## Estructura

```
src/dominio            métricas y entidades; no conoce ningún modelo de pronóstico
src/aplicacion         casos de uso y puertos
src/infraestructura    adaptadores: modelos, persistencia, estadística, web
herramientas/          scripts del experimento
pruebas/               batería de 32 pruebas
```
