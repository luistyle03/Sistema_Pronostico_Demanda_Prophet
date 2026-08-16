"""[S10 · Iteración 1] Núcleo del hexágono + adaptador Prophet.
El caso de uso se prueba con un doble (sin Prophet): evidencia de la
inversión de dependencias. El adaptador real se prueba aparte."""

from datetime import date, timedelta

import pytest

from src.aplicacion.casos_uso.generar_pronostico import (
    MINIMO_HISTORICO,
    GeneradorDePronostico,
)
from src.aplicacion.puertos import PuertoModeloPronostico
from src.dominio.entidades import Pronostico, PuntoSerie, SerieTemporal
from src.dominio.excepciones import SerieMuyCortaError
from src.infraestructura.modelos.adaptador_prophet import AdaptadorProphet
from src.infraestructura.modelos.utilidades import fechas_futuras


def serie_constante(n, valor=10.0, inicio=date(2026, 1, 1)):
    return SerieTemporal(
        "prueba", [PuntoSerie(inicio + timedelta(days=i), valor) for i in range(n)]
    )


class ModeloConstante(PuertoModeloPronostico):
    def __init__(self, c, etiqueta="constante"):
        self._c, self._etq, self._ultima = c, etiqueta, None

    @property
    def nombre(self):
        return self._etq

    def entrenar(self, serie):
        self._ultima = serie.fechas()[-1]

    def pronosticar(self, horizonte):
        return Pronostico(self._etq, fechas_futuras(self._ultima, horizonte), [self._c] * horizonte)


def test_dividir_rechaza_particiones_imposibles():
    s = serie_constante(10)
    with pytest.raises(SerieMuyCortaError):
        s.dividir(0)
    with pytest.raises(SerieMuyCortaError):
        s.dividir(10)


def test_generador_exige_minimo_historico():
    caso = GeneradorDePronostico()
    with pytest.raises(SerieMuyCortaError):
        caso.ejecutar(ModeloConstante(10), serie_constante(MINIMO_HISTORICO - 1), 7)
    with pytest.raises(SerieMuyCortaError):
        caso.ejecutar(ModeloConstante(10), serie_constante(28), 0)


def test_generador_resumen_gerencial_correcto():
    caso = GeneradorDePronostico()
    pron, resumen = caso.ejecutar(ModeloConstante(10.0), serie_constante(28, 10.0), 7)
    assert pron.fechas[0] == date(2026, 1, 28) + timedelta(days=1)
    assert resumen.total_proyectado == pytest.approx(70.0)
    assert resumen.total_periodo_anterior == pytest.approx(70.0)
    assert resumen.variacion_porcentual == pytest.approx(0.0)
    assert resumen.promedio_diario == pytest.approx(10.0)


def test_adaptador_prophet_cumple_contrato():
    import numpy as np

    rng = np.random.default_rng(42)
    inicio = date(2024, 1, 1)
    puntos = []
    for i in range(730):
        f = inicio + timedelta(days=i)
        semana = (1.0, 0.9, 0.9, 1.0, 1.2, 1.6, 1.4)[f.weekday()]
        puntos.append(PuntoSerie(f, max(0.0, float(rng.normal((20 + 0.01 * i) * semana, 2)))))
    serie = SerieTemporal("sintetica", puntos)
    modelo = AdaptadorProphet()  # parámetros por defecto del DTO
    modelo.entrenar(serie)
    pron = modelo.pronosticar(30)
    assert len(pron.valores) == 30
    assert all(v >= 0 for v in pron.valores)
    assert pron.fechas[0] == serie.fechas()[-1] + timedelta(days=1)
    assert {(b - a).days for a, b in zip(pron.fechas, pron.fechas[1:])} == {1}
    assert pron.limites_inferiores is not None and len(pron.limites_superiores) == 30
