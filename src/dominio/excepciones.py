"""
CAPA DE DOMINIO — Excepciones del negocio.

Definir excepciones propias (en lugar de usar ValueError genérico) permite
que las capas externas distingan "el usuario subió un archivo mal armado"
(error 400, mensaje amable) de "el sistema se rompió" (error 500).
"""


class ErrorDeDominio(Exception):
    """Raíz de todos los errores del negocio. Su mensaje es apto para mostrarse al usuario."""


class DatosInvalidosError(ErrorDeDominio):
    """El archivo o los parámetros recibidos no cumplen el formato esperado."""


class ColumnasFaltantesError(DatosInvalidosError):
    """El archivo no contiene las columnas mínimas (fecha, unidades, ...)."""


class SerieMuyCortaError(DatosInvalidosError):
    """La serie no tiene suficientes observaciones para entrenar y evaluar."""


class SerieNoElegibleError(DatosInvalidosError):
    """
    RF03: la serie no alcanza la historia mínima de 365 días continuos para
    un pronóstico confiable. Al heredar de DatosInvalidosError, el servidor
    la traduce a un HTTP 400 con mensaje claro (advertencia de elegibilidad).
    """


class ModeloNoEntrenadoError(ErrorDeDominio):
    """Se pidió pronosticar antes de llamar a entrenar()."""
