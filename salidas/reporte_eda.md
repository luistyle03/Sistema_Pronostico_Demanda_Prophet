# Reporte de exploración y limpieza del dataset — Semana S9
[PXP: Fase de Exploración] · Tesis SPD · Semilla: 42

> **AVISO:** reporte del modo `--demo` (datos sintéticos), solo para validar el script. Las cifras reales salen de ejecutar con `--fuente train.csv`.

## 1. Archivo fuente
| Métrica | Valor |
|---|---|
| Filas leídas | 105,738 |
| Periodo cubierto | 2013-01-01 a 2015-06-30 |
| Tiendas en el archivo | 14 |
| Pares tienda-producto evaluados | 126 |
| Series de la muestra | 50 (10 tiendas × 5 productos) |

## 2. Criterios de inclusión y muestreo (Plan de Tesis, §7.3)
**Inclusión:** promedio ≥ 30 unidades/día y ≤ 15% de días
sin venta. Se excluye la demanda intermitente (Croston, 1972; Syntetos y Boylan, 2005),
que requiere métodos especializados ajenos a los cinco modelos comparados.
**Muestreo aleatorio estratificado en dos etapas** (Lohr, 2010), semilla 42:
etapa 1, 10 tiendas sorteadas entre las que tienen ≥ 5 productos elegibles;
etapa 2, 5 productos elegibles sorteados por tienda (pueden diferir entre tiendas).

- Tienda 1: productos [101, 102, 106, 107, 108]
- Tienda 2: productos [101, 104, 105, 107, 109]
- Tienda 3: productos [104, 105, 106, 107, 109]
- Tienda 4: productos [103, 104, 105, 107, 108]
- Tienda 5: productos [101, 103, 104, 106, 108]
- Tienda 6: productos [101, 102, 103, 105, 108]
- Tienda 10: productos [101, 102, 103, 104, 106]
- Tienda 11: productos [101, 104, 105, 106, 109]
- Tienda 12: productos [101, 102, 103, 105, 107]
- Tienda 14: productos [101, 104, 106, 107, 109]

## 3. Diccionario de datos (dataset_limpio.csv)
| Columna | Tipo | Descripción |
|---|---|---|
| fecha | fecha (AAAA-MM-DD) | día calendario, serie continua sin huecos |
| tienda | entero | identificador de la tienda |
| producto | entero | identificador del producto |
| unidades | decimal ≥ 0 | unidades vendidas en el día |

## 4. Decisiones de limpieza aplicadas
| N.º | Situación | Regla | Casos |
|---|---|---|---|
| D1 | Días sin registro | Se rellenan con 0: en retail la ausencia de fila es "no hubo venta" | 3,620 |
| D2 | Ventas netas negativas | Se truncan a 0: la variable de estudio es la demanda de venta | 186 |
| D3 | Picos atípicos (> Q3 + 3·RIC) | Se detectan y reportan pero SE CONSERVAN: son demanda real | 130 |

## 5. Estadísticos por serie (primeras 10)
|   tienda |   producto |   dias |   media |   mediana |   pct_ceros |
|---------:|-----------:|-------:|--------:|----------:|------------:|
|        1 |        101 |    911 |  108.68 |       123 |         9.2 |
|        1 |        102 |    911 |   77.02 |        76 |         7.1 |
|        1 |        106 |    911 |   57.64 |        60 |        10.3 |
|        1 |        107 |    911 |   71.43 |        74 |         6.7 |
|        1 |        108 |    911 |   83.86 |        88 |         8.6 |
|        2 |        101 |    911 |  168.79 |       188 |         9   |
|        2 |        104 |    911 |  150.15 |       166 |         7.2 |
|        2 |        105 |    911 |  123.25 |       133 |         9.4 |
|        2 |        107 |    911 |   73.82 |        75 |         6.7 |
|        2 |        109 |    911 |  164.13 |       174 |         8.3 |

*(tabla completa en series_resumen.csv — reproducible con la misma semilla)*
