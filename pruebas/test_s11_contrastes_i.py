"""[S11 · Iteración 2] Contrastes I: promedio móvil y Holt-Winters."""

from datetime import date, timedelta

import pytest

from src.dominio.entidades import PuntoSerie, SerieTemporal
from src.dominio.excepciones import ModeloNoEntrenadoError, SerieMuyCortaError
from src.infraestructura.modelos.adaptador_holt_winters import AdaptadorHoltWinters
from src.infraestructura.modelos.adaptador_media_movil import AdaptadorMediaMovil


def serie(valores, inicio=date(2026, 1, 1)):
    return SerieTemporal(
        "s", [PuntoSerie(inicio + timedelta(days=i), float(v)) for i, v in enumerate(valores)]
    )


def test_media_movil_de_serie_constante_es_constante():
    m = AdaptadorMediaMovil(ventana=7)
    m.entrenar(serie([4.0] * 30))
    p = m.pronosticar(10)
    assert p.valores == [4.0] * 10
    assert p.fechas[0] == date(2026, 1, 30) + timedelta(days=1)


def test_media_movil_exige_ventana_completa_y_entrenamiento():
    m = AdaptadorMediaMovil(ventana=7)
    with pytest.raises(SerieMuyCortaError):
        m.entrenar(serie([1, 2, 3, 4, 5]))
    with pytest.raises(ModeloNoEntrenadoError):
        AdaptadorMediaMovil().pronosticar(5)


def test_holt_winters_cumple_contrato_con_patron_semanal():
    valores = [(10, 9, 9, 10, 12, 16, 14)[i % 7] for i in range(56)]  # 8 semanas
    m = AdaptadorHoltWinters(periodo_estacional=7)
    m.entrenar(serie(valores))
    p = m.pronosticar(14)
    assert len(p.valores) == 14 and all(v >= 0 for v in p.valores)


def test_holt_winters_degrada_con_serie_corta():
    m = AdaptadorHoltWinters(periodo_estacional=7)
    m.entrenar(serie([5, 6, 7, 8, 9, 10, 11, 12, 13, 14]))  # < 2 ciclos
    assert len(m.pronosticar(5).valores) == 5
