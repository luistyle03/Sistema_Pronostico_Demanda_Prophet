"""[HU02 · RF06] Vista de descomposición: el sistema muestra POR QUÉ pronostica.
El adaptador Prophet expone las componentes de su ecuación aditiva (tendencia,
perfil semanal, perfil anual, feriados) y el endpoint las publica para la
rejilla 2x2 de la pantalla. Con un motor sin descomposición el campo viaja como
null y la interfaz oculta la vista: misma puerta, capacidad opcional."""

import io
from datetime import date, timedelta

from test_s14_lector_y_pantallas import app_de_prueba, xlsx_bytes

from src.aplicacion.casos_uso.evaluar_modelos import EvaluadorDeModelos
from src.aplicacion.casos_uso.generar_pronostico import GeneradorDePronostico
from src.aplicacion.parametros import ParametrosPronostico
from src.aplicacion.puertos import PuertoModeloPronostico
from src.dominio.entidades import (
    ComponentesPronostico,
    Pronostico,
    PuntoSerie,
    SerieTemporal,
)
from src.infraestructura.modelos.adaptador_media_movil import AdaptadorMediaMovil
from src.infraestructura.modelos.utilidades import fechas_futuras
from src.infraestructura.persistencia.exportador_excel import ExportadorExcel
from src.infraestructura.persistencia.lector_archivos import LectorVentas
from src.infraestructura.web.servidor import crear_app


def serie_retail(n_dias=730):
    """Dos años de ventas con patrón de fin de semana: elegible (RF03) y con
    señal semanal clara para que Prophet tenga algo real que descomponer."""
    inicio = date(2024, 1, 1)
    puntos = []
    for i in range(n_dias):
        fecha = inicio + timedelta(days=i)
        base = 20.0 + (8.0 if fecha.weekday() >= 5 else 0.0)  # sábado y domingo
        puntos.append(PuntoSerie(fecha, base + i * 0.01))  # leve tendencia
    return SerieTemporal("Bodega", puntos)


def test_adaptador_prophet_expone_las_cuatro_componentes():
    from src.infraestructura.modelos.adaptador_prophet import AdaptadorProphet

    parametros = ParametrosPronostico(
        feriados_personalizados=[(date(2025, 7, 28), "Fiestas Patrias")]
    )
    modelo = AdaptadorProphet(parametros)
    serie = serie_retail()
    modelo.entrenar(serie)
    pronostico = modelo.pronosticar(14)

    comp = pronostico.componentes
    assert isinstance(comp, ComponentesPronostico)
    assert len(comp.fechas) == len(serie) + 14  # historia + futuro
    assert len(comp.tendencia) == len(comp.fechas)  # tendencia sobre todo el rango
    assert len(comp.perfil_semanal) == 7  # lunes .. domingo
    assert len(comp.perfil_anual) >= 360  # un año de perfil (mm-dd)
    assert comp.feriados is not None  # hay feriado configurado
    assert max(abs(v) for v in comp.feriados) > 0  # y su efecto no es nulo
    # El patrón inyectado (fin de semana alto) debe reflejarse en el perfil:
    assert max(comp.perfil_semanal[5], comp.perfil_semanal[6]) > min(comp.perfil_semanal[:5])


class MotorConComponentes(PuertoModeloPronostico):
    """Doble de prueba: cumple el puerto y ofrece una descomposición fija, para
    verificar la serialización del endpoint sin pagar el costo de Prophet."""

    def __init__(self):
        self._ultima = None

    @property
    def nombre(self):
        return "doble-con-componentes"

    def entrenar(self, serie):
        self._ultima = serie

    def pronosticar(self, horizonte):
        fechas = fechas_futuras(self._ultima.fechas()[-1], horizonte)
        todas = self._ultima.fechas() + fechas
        return Pronostico(
            self.nombre,
            fechas,
            [9.0] * horizonte,
            componentes=ComponentesPronostico(
                fechas=todas,
                tendencia=[1.0] * len(todas),
                perfil_semanal=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
                perfil_anual_dias=["01-01", "07-28"],
                perfil_anual=[-1.0, 2.5],
                feriados=[0.0] * len(todas),
            ),
        )


def app_con_motor(motor):
    return crear_app(
        evaluador=EvaluadorDeModelos([AdaptadorMediaMovil()]),
        generador=GeneradorDePronostico(),
        fabrica_modelo=lambda parametros: motor,
        lector=LectorVentas(),
        exportador=ExportadorExcel(),
    )


def carga_elegible():
    inicio = date(2025, 1, 1)
    filas = [(inicio + timedelta(days=i), "Gaseosa 500ml", 5 + i % 4) for i in range(400)]
    return xlsx_bytes(filas)


def _cargar_y_generar(cliente):
    r1 = cliente.post(
        "/api/pronostico/cargar",
        data={"archivo": (io.BytesIO(carga_elegible()), "ventas.xlsx")},
        content_type="multipart/form-data",
    )
    token = r1.get_json()["token_datos"]
    return cliente.post(
        "/api/pronostico/generar",
        json={"token_datos": token, "producto": "Gaseosa 500ml", "horizonte": 7},
    )


def test_endpoint_publica_las_componentes_del_modelo():
    r = _cargar_y_generar(app_con_motor(MotorConComponentes()).test_client())
    assert r.status_code == 200
    comp = r.get_json()["componentes"]
    assert comp["semanal"]["dias"] == ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    assert comp["semanal"]["valores"][-1] == 0.7
    assert comp["anual"]["dias"] == ["01-01", "07-28"]
    # Recorte de legibilidad del servidor: 365 días de historia + 7 de horizonte.
    assert len(comp["tendencia"]["fechas"]) == len(comp["tendencia"]["valores"]) == 372
    assert comp["feriados"] is not None


def test_endpoint_publica_null_con_motor_sin_descomposicion():
    r = _cargar_y_generar(app_de_prueba().test_client())  # promedio móvil
    assert r.status_code == 200
    assert r.get_json()["componentes"] is None  # la interfaz oculta la vista
