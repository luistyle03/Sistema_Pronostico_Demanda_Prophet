"""
HERRAMIENTA — Validación del instrumento de medición (las métricas del software).

Aporta DOS evidencias de validez sobre el módulo real `src/dominio/metricas.py`:

  (A) Verificación contra valores conocidos (calculados a mano):
      confirma que cada función implementa la fórmula pretendida.
      -> protege de errores de PROGRAMACIÓN.

  (B) Validación concurrente contra una herramienta establecida (scikit-learn):
      confirma que el resultado coincide con el estándar de la comunidad.
      -> protege de errores de CONCEPTO (mala interpretación de la fórmula).

Referencias: Hernández-Sampieri & Mendoza (2018) [validez de contenido y de
criterio concurrente]; IEEE Std 1012 [verificación y validación]; ISO/IEC 25010
[corrección funcional]; Hyndman & Koehler (2006) y Makridakis et al. (2022)
[definiciones de las métricas].

Uso:
    pip install scikit-learn numpy pandas
    python herramientas/validacion_instrumento.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Importar el paquete del proyecto aunque se ejecute directamente.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sklearn.metrics import mean_absolute_error, mean_squared_error  # noqa: E402

from entorno import imprimir_entorno
from src.dominio import metricas  # noqa: E402


def aprox(obtenido: float, esperado: float, tol: float = 1e-6) -> bool:
    return abs(obtenido - esperado) <= tol * max(1.0, abs(esperado))


# ===========================================================================
# (A) VERIFICACIÓN CONTRA VALORES CONOCIDOS (calculados a mano)
# ===========================================================================
def verificacion_valores_conocidos() -> list[dict]:
    """
    Cada caso trae el cálculo a mano en el comentario para que sea auditable.
    reales = [10, 10, 10] ; pronóstico = [8, 12, 10]
      MAE   = (|10-8|+|10-12|+|10-10|)/3 = (2+2+0)/3      = 1.333333
      Sesgo = ((10-8)+(10-12)+(10-10))/3 = (2-2+0)/3       = 0.0
      WAPE  = (2+2+0)/(10+10+10)*100     = 4/30*100        = 13.333333
      MAPE  = (0.2+0.2+0)/3*100          = 0.4/3*100       = 13.333333
      RMSE  = sqrt((4+4+0)/3) = sqrt(8/3)                  = 1.632993
    RMSSE: entren = [10,12,10,12,10] ; reales=[10,10] ; pred=[8,12]
      ECM_modelo  = ((10-8)^2+(10-12)^2)/2 = (4+4)/2 = 4
      ECM_ingenuo = media de [2^2,2^2,2^2,2^2]        = 4
      RMSSE = sqrt(4/4)                                    = 1.0
    """
    r = [10.0, 10.0, 10.0]
    p = [8.0, 12.0, 10.0]
    entren = [10.0, 12.0, 10.0, 12.0, 10.0]
    casos = [
        ("MAE", "unidades", metricas.mae(r, p), 1.333333),
        ("Sesgo", "unidades", metricas.sesgo(r, p), 0.0),
        ("WAPE", "%", metricas.wape(r, p), 13.333333),
        ("MAPE", "%", metricas.mape(r, p), 13.333333),
        ("RMSE", "unidades", metricas.rmse(r, p), 1.632993),
        ("RMSSE", "ratio", metricas.rmsse(entren, [10.0, 10.0], [8.0, 12.0]), 1.0),
    ]
    filas = []
    for nombre, unidad, obtenido, esperado in casos:
        ok = aprox(obtenido, esperado, tol=1e-5)
        filas.append(
            {
                "Métrica": nombre,
                "Unidad": unidad,
                "Esperado (a mano)": round(esperado, 6),
                "Software": round(obtenido, 6),
                "Resultado": "OK - coincide" if ok else "X - difiere",
            }
        )
    return filas


# ===========================================================================
# (B) VALIDACIÓN CONCURRENTE CONTRA scikit-learn
# ===========================================================================
def validacion_concurrente() -> list[dict]:
    """Mismos datos en el software y en referencias externas; deben coincidir.

    MAE y RMSE se contrastan contra scikit-learn. El sesgo, el WAPE y el RMSSE
    no existen en esa libreria, de modo que se contrastan contra oraculos
    independientes implementados con numpy desde la definicion publicada.
    """
    rng = np.random.default_rng(2026)
    reales = rng.uniform(5, 100, size=200)
    pred = reales + rng.normal(0, 8, size=200)  # pronóstico con error realista

    filas = []
    # MAE
    sw_mae = metricas.mae(list(reales), list(pred))
    sk_mae = mean_absolute_error(reales, pred)
    filas.append(("MAE", sw_mae, sk_mae, "sklearn.metrics.mean_absolute_error"))
    # RMSE
    sw_rmse = metricas.rmse(list(reales), list(pred))
    sk_rmse = math.sqrt(mean_squared_error(reales, pred))
    filas.append(("RMSE", sw_rmse, sk_rmse, "sqrt(sklearn.metrics.mean_squared_error)"))
    # Sesgo (Mean Error) — sklearn no lo trae; se compara con numpy directo.
    sw_sesgo = metricas.sesgo(list(reales), list(pred))
    np_sesgo = float(np.mean(reales - pred))
    filas.append(("Sesgo", sw_sesgo, np_sesgo, "numpy: mean(real - pred)"))

    # RMSSE y WAPE no existen en scikit-learn. Para que la validacion concurrente
    # los cubra igualmente se construyen ORACULOS INDEPENDIENTES con numpy: son
    # implementaciones escritas desde la definicion publicada, sin reutilizar una
    # sola linea del modulo bajo prueba. Sin esto, las dos metricas principales
    # del estudio quedaban acreditadas unicamente contra el calculo manual, que
    # no descarta un malentendido conceptual compartido entre el investigador y
    # su implementacion.
    # WAPE = 100 * suma|real - pred| / suma(real)   (Hyndman y Koehler, 2006)
    sw_wape = metricas.wape(list(reales), list(pred))
    np_wape = float(100.0 * np.abs(reales - pred).sum() / reales.sum())
    filas.append(("WAPE", sw_wape, np_wape, "numpy: 100*sum|e|/sum(y)"))
    # RMSSE = sqrt( MSE_modelo / MSE_ingenuo_de_un_paso_en_entrenamiento )  (M5)
    entrenamiento = rng.uniform(5, 100, size=300)
    sw_rmsse = metricas.rmsse(list(entrenamiento), list(reales), list(pred))
    mse_modelo = float(np.mean((reales - pred) ** 2))
    mse_naive1 = float(np.mean(np.diff(entrenamiento) ** 2))
    np_rmsse = float(np.sqrt(mse_modelo / mse_naive1))
    filas.append(("RMSSE", sw_rmsse, np_rmsse, "numpy: sqrt(MSE / MSE naive-1)"))

    salida = []
    for nombre, sw, ref, herramienta in filas:
        ok = aprox(sw, ref, tol=1e-6)
        salida.append(
            {
                "Métrica": nombre,
                "Software": round(sw, 6),
                "Referencia": round(ref, 6),
                "Herramienta": herramienta,
                "Resultado": "OK - coincide" if ok else "X - difiere",
            }
        )
    return salida


def main() -> None:
    print("=" * 74)
    print("VALIDACIÓN DEL INSTRUMENTO DE MEDICIÓN — módulo src/dominio/metricas.py")
    print("=" * 74)

    a = verificacion_valores_conocidos()
    print("\n(A) VERIFICACIÓN CONTRA VALORES CONOCIDOS (calculados a mano)")
    print(pd.DataFrame(a).to_string(index=False))

    b = validacion_concurrente()
    print("\n(B) VALIDACIÓN CONCURRENTE CONTRA scikit-learn / numpy")
    print(pd.DataFrame(b).to_string(index=False))

    todos_ok = all("OK" in f["Resultado"] for f in a + b)
    print("\n" + "-" * 74)
    print(
        "VEREDICTO:",
        (
            "INSTRUMENTO VÁLIDO — todas las métricas coinciden."
            if todos_ok
            else "REVISAR — alguna métrica no coincide."
        ),
    )

    # Guardar la evidencia para el anexo de metodología.
    salida = Path("validacion_instrumento.xlsx")
    with pd.ExcelWriter(salida) as w:
        pd.DataFrame(a).to_excel(w, sheet_name="A - Valores conocidos", index=False)
        pd.DataFrame(b).to_excel(w, sheet_name="B - Validez concurrente", index=False)
    print(f"Evidencia guardada en: {salida}")


if __name__ == "__main__":
    imprimir_entorno()
    main()
