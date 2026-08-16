"""[S12 · Iteración 3] Contrastes II: regresión lineal y auto-ARIMA (AIC)."""

from datetime import date, timedelta

import pytest

from src.dominio.entidades import PuntoSerie, SerieTemporal
from src.dominio.excepciones import ModeloNoEntrenadoError
from src.infraestructura.modelos.adaptador_arima import AdaptadorARIMA
from src.infraestructura.modelos.adaptador_regresion_lineal import AdaptadorRegresionLineal


def serie(valores, inicio=date(2026, 1, 1)):
    return SerieTemporal(
        "s", [PuntoSerie(inicio + timedelta(days=i), float(v)) for i, v in enumerate(valores)]
    )


def test_regresion_recupera_una_tendencia_perfecta():
    m = AdaptadorRegresionLineal()
    m.entrenar(serie([2.0 * t for t in range(40)]))  # y = 2t exacta
    p = m.pronosticar(5)
    assert p.valores == pytest.approx([80.0, 82.0, 84.0, 86.0, 88.0], abs=1e-6)


def test_regresion_exige_entrenamiento():
    with pytest.raises(ModeloNoEntrenadoError):
        AdaptadorRegresionLineal().pronosticar(3)


def test_arima_selecciona_orden_y_cumple_contrato():
    import numpy as np

    rng = np.random.default_rng(7)
    m = AdaptadorARIMA()
    m.entrenar(serie([20 + float(r) for r in rng.normal(0, 2, 90)]))
    assert m.orden_elegido is not None  # auditoría del AIC
    p = m.pronosticar(7)
    assert len(p.valores) == 7 and all(v >= 0 for v in p.valores)
