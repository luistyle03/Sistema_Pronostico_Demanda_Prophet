"""[S13 · Iteración 4] Instrumento de medición: métricas, evaluador y estadística.
Las métricas se contrastan contra cálculos A MANO (validez de contenido)."""

import math
from datetime import date, timedelta

import pytest
from test_s10_nucleo_y_prophet import ModeloConstante

from src.aplicacion.casos_uso.evaluar_modelos import EvaluadorDeModelos
from src.dominio import metricas
from src.dominio.entidades import PuntoSerie, SerieTemporal
from src.dominio.excepciones import SerieMuyCortaError
from src.infraestructura.estadistica.adaptador_scipy import AdaptadorPruebasScipy


def test_metricas_contra_calculo_manual():
    reales, pron = [10.0, 20.0], [8.0, 24.0]
    assert metricas.mae(reales, pron) == pytest.approx(3.0)  # (2+4)/2
    assert metricas.wape(reales, pron) == pytest.approx(20.0)  # 6/30·100
    assert metricas.sesgo(reales, pron) == pytest.approx(-1.0)  # (2-4)/2
    assert metricas.rmse(reales, pron) == pytest.approx(math.sqrt(10.0))
    assert metricas.mape([0.0, 10.0], [5.0, 8.0]) == pytest.approx(20.0)  # excluye el 0
    # RMSSE: denominador ingenuo de [1,2,3] = 1; numerador = (1²+2²)/2 = 2.5
    assert metricas.rmsse([1.0, 2.0, 3.0], [4.0, 5.0], [3.0, 3.0]) == pytest.approx(math.sqrt(2.5))


def test_evaluador_calcula_al_ganador_no_lo_predefine():
    valores = [(8.0, 12.0)[i % 2] for i in range(45)]
    serie = SerieTemporal(
        "alterna",
        [PuntoSerie(date(2026, 1, 1) + timedelta(days=i), v) for i, v in enumerate(valores)],
    )
    evaluador = EvaluadorDeModelos([ModeloConstante(10.0, "c10"), ModeloConstante(0.0, "c0")])
    resultado = evaluador.ejecutar(serie, horizonte=5)
    assert resultado.ganador.nombre_modelo == "c10"  # menor RMSSE, calculado
    assert resultado.resultados[0].mae < resultado.resultados[1].mae


def test_evaluador_exige_entrenamiento_minimo():
    corta = SerieTemporal(
        "corta",
        [PuntoSerie(date(2026, 1, 1) + timedelta(days=i), 5.0) for i in range(20)],
    )
    with pytest.raises(SerieMuyCortaError):
        EvaluadorDeModelos([ModeloConstante(1.0)]).ejecutar(corta, horizonte=5)


def test_pruebas_pareadas_scipy_devuelven_valores_validos():
    r = AdaptadorPruebasScipy().comparar_pareado(
        "A vs B", [1.0, 2.0, 3.0, 4.0, 5.0], [1.5, 3.1, 3.9, 5.2, 5.8]
    )
    assert 0.0 <= r.p_valor_t <= 1.0 and 0.0 <= r.p_valor_wilcoxon <= 1.0
    assert r.d_cohen > 0 and math.isfinite(r.d_cohen) and r.n == 5


def test_ajuste_holm_contra_valores_calculados_a_mano():
    from herramientas.contraste_hipotesis import ajuste_holm

    # p ordenados: 0.01, 0.03, 0.04, 0.20 -> 4·0.01=0.04; 3·0.03=0.09;
    # 2·0.04=0.08 se eleva a 0.09 por monotonía; 1·0.20=0.20
    assert ajuste_holm([0.01, 0.04, 0.03, 0.20]) == pytest.approx([0.04, 0.09, 0.09, 0.20])


def test_contraste_he1_confirma_cuando_rmsse_es_menor_a_uno():
    import numpy as np

    from herramientas.contraste_hipotesis import contraste_he1

    rng = np.random.default_rng(42)
    rmsse = [float(x) for x in rng.normal(0.85, 0.05, 40)]
    resultado = contraste_he1(rmsse)
    assert resultado["p_valor"] < 0.05
    assert resultado["proporcion_rmsse_menor_1"] > 0.95
    assert "confirmada" in resultado["decision"]
