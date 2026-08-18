"""
CAPA DE INFRAESTRUCTURA — Lector de archivos de ventas (Excel y CSV).

Convierte el archivo que sube el usuario en objetos del dominio
(SerieTemporal). Acepta nombres de columna flexibles (con o sin tildes,
mayúsculas o minúsculas) y aplica dos reglas de saneamiento documentadas:

1. Si un mismo producto tiene varias filas en la misma fecha, se SUMAN.
2. Los días calendario sin registro se rellenan con 0 (se asume que un día
   ausente es un día sin ventas), para que la serie sea diaria y continua.
"""

from __future__ import annotations

import io
import unicodedata
from typing import List, Optional

import pandas as pd

from src.dominio.entidades import DIAS_MINIMOS_ELEGIBLE, PuntoSerie, SerieTemporal
from src.dominio.excepciones import ColumnasFaltantesError, DatosInvalidosError

# Sinónimos aceptados para cada columna lógica (ya normalizados: ver _normalizar).
NOMBRES_FECHA = {"fecha", "date", "dia", "ds"}
NOMBRES_PRODUCTO = {
    "producto",
    "nombre_producto",
    "nombre_del_producto",
    "item",
    "articulo",
    "serie",
    "sku",
}
NOMBRES_UNIDADES = {
    "unidades_vendidas",
    "unidades",
    "ventas",
    "cantidad",
    "unit_sales",
    "demanda",
    "y",
    "valor",
}


def _normalizar(texto: str) -> str:
    """'  Unidades Vendidas ' -> 'unidades_vendidas' (sin tildes ni espacios)."""
    sin_tildes = unicodedata.normalize("NFKD", str(texto))
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return sin_tildes.strip().lower().replace(" ", "_")


class LectorVentas:
    """Adaptador de entrada: archivo del usuario -> tabla limpia -> series."""

    def leer(self, contenido: bytes, nombre_archivo: str) -> pd.DataFrame:
        """
        Lee los bytes del archivo y devuelve un DataFrame estandarizado con
        columnas: fecha (datetime), producto (texto, opcional), unidades (float).
        """
        tabla = self._abrir(contenido, nombre_archivo)
        if tabla.empty:
            raise DatosInvalidosError("El archivo no contiene filas de datos.")
        # --- Mapear las columnas reales a las columnas lógicas ----------------
        mapa = {}
        for columna in tabla.columns:
            clave = _normalizar(columna)
            if clave in NOMBRES_FECHA and "fecha" not in mapa.values():
                mapa[columna] = "fecha"
            elif clave in NOMBRES_PRODUCTO and "producto" not in mapa.values():
                mapa[columna] = "producto"
            elif clave in NOMBRES_UNIDADES and "unidades" not in mapa.values():
                mapa[columna] = "unidades"
        tabla = tabla.rename(columns=mapa)
        faltantes = {"fecha", "unidades"} - set(tabla.columns)
        if faltantes:
            raise ColumnasFaltantesError(
                "No se encontraron las columnas requeridas: "
                f"{', '.join(sorted(faltantes))}. Columnas leídas: "
                f"{', '.join(str(c) for c in tabla.columns)}. "
                "Se esperan: fecha, nombre de producto (opcional) y unidades vendidas."
            )
        # --- Convertir y validar la columna fecha -----------------------------
        # dayfirst=True: en Perú '02/03/2026' significa 2 de marzo, no 3 de febrero.
        tabla["fecha"] = pd.to_datetime(tabla["fecha"], errors="coerce", dayfirst=True)
        invalidas = int(tabla["fecha"].isna().sum())
        if invalidas:
            raise DatosInvalidosError(
                f"{invalidas} fila(s) tienen una fecha que no se pudo interpretar. "
                "Use fechas reales de Excel o el formato dd/mm/aaaa."
            )
        # --- Convertir y validar la columna unidades ---------------------------
        tabla["unidades"] = pd.to_numeric(tabla["unidades"], errors="coerce")
        no_numericas = int(tabla["unidades"].isna().sum())
        if no_numericas:
            raise DatosInvalidosError(
                f"{no_numericas} fila(s) tienen unidades vendidas no numéricas."
            )
        # Devoluciones (negativos) se tratan como 0: la demanda no es negativa.
        tabla.loc[tabla["unidades"] < 0, "unidades"] = 0.0
        columnas = (
            ["fecha", "producto", "unidades"]
            if "producto" in tabla.columns
            else ["fecha", "unidades"]
        )
        return tabla[columnas]

    def _abrir(self, contenido: bytes, nombre_archivo: str) -> pd.DataFrame:
        """Elige el lector según la extensión del archivo subido."""
        nombre = nombre_archivo.lower()
        flujo = io.BytesIO(contenido)  # Los bytes en memoria se leen como archivo.
        try:
            if nombre.endswith((".xlsx", ".xlsm", ".xls")):
                return pd.read_excel(flujo)
            if nombre.endswith(".csv"):
                return pd.read_csv(flujo)
        except Exception as exc:
            raise DatosInvalidosError(f"No se pudo leer el archivo: {exc}") from exc
        raise DatosInvalidosError("Formato no soportado. Suba un archivo .xlsx o .csv.")

    def productos(self, tabla: pd.DataFrame) -> List[str]:
        """Lista ordenada de productos presentes en el archivo (si hay columna)."""
        if "producto" not in tabla.columns:
            return []
        return sorted(tabla["producto"].astype(str).str.strip().unique().tolist())

    def productos_con_elegibilidad(self, tabla: pd.DataFrame) -> List[dict]:
        """
        RF03 — Detecta la elegibilidad de cada serie del archivo: cuántos días
        de calendario continuo abarca (de su primera a su última fecha, igual
        que construir_serie) y si alcanza el mínimo del dominio (365). El
        umbral NO se decide aquí: se importa de la capa de dominio.

        Devuelve una lista de {"nombre", "dias", "elegible"} por producto; si
        el archivo no trae columna de producto, un único elemento del total
        agregado con la marca "agregado": True.
        """

        def _dias(datos: pd.DataFrame) -> int:
            return int((datos["fecha"].max() - datos["fecha"].min()).days) + 1

        nombres = self.productos(tabla)
        if not nombres:
            dias = _dias(tabla)
            return [
                {
                    "nombre": "Todos los productos",
                    "dias": dias,
                    "elegible": dias >= DIAS_MINIMOS_ELEGIBLE,
                    "agregado": True,
                }
            ]
        columna = tabla["producto"].astype(str).str.strip()
        resultado = []
        for nombre in nombres:
            dias = _dias(tabla[columna == nombre])
            resultado.append(
                {
                    "nombre": nombre,
                    "dias": dias,
                    "elegible": dias >= DIAS_MINIMOS_ELEGIBLE,
                }
            )
        return resultado

    def construir_serie(self, tabla: pd.DataFrame, producto: Optional[str] = None) -> SerieTemporal:
        """
        Filtra (si se pidió un producto), suma por fecha y rellena los huecos
        del calendario con 0 para obtener una serie diaria continua.
        """
        datos = tabla
        nombre = "Todos los productos"
        if producto and "producto" in tabla.columns:
            datos = tabla[tabla["producto"].astype(str).str.strip() == producto]
            nombre = producto
            if datos.empty:
                raise DatosInvalidosError(f"El producto '{producto}' no tiene filas.")
        # Regla 1: sumar las filas que comparten fecha.
        agregada = datos.groupby("fecha", as_index=True)["unidades"].sum().sort_index()
        # Regla 2: calendario continuo entre la primera y la última fecha.
        calendario = pd.date_range(agregada.index.min(), agregada.index.max(), freq="D")
        continua = agregada.reindex(calendario, fill_value=0.0)
        puntos = [
            PuntoSerie(fecha=marca.date(), valor=float(valor)) for marca, valor in continua.items()
        ]
        return SerieTemporal(nombre=nombre, puntos=puntos)

    def construir_series_lote(self, tabla: pd.DataFrame) -> List[SerieTemporal]:
        """
        Para el Módulo 1 en modo lote: una SerieTemporal por cada valor de la
        columna producto/serie. Si no existe esa columna, devuelve una sola
        serie agregada (modo de serie única).
        """
        nombres = self.productos(tabla)
        if not nombres:
            return [self.construir_serie(tabla)]
        return [self.construir_serie(tabla, nombre) for nombre in nombres]
