/* =====================================================================
   Módulo 1 (experimental) — Lógica del navegador.
   Métrica PRINCIPAL: RMSSE (libre de escala, comparable entre productos
   de distinto volumen; RMSSE < 1 = mejor que el método ingenuo).
   Métricas de apoyo: WAPE (% ponderado por volumen, estándar retail),
   MAE (unidades), sesgo (dirección del error), MAPE y RMSE.
   ===================================================================== */
"use strict";

const COLORES = {
  "Prophet": "#0E2A47",
  "ARIMA": "#C0563B",
  "Holt-Winters": "#3C7A57",
  "Promedio móvil": "#7A6AAE",
  "Regresión lineal": "#8A8F98"
};
const DORADO = "#D9A441";

const $ = (id) => document.getElementById(id);

function mostrarEstado(texto, clase) {
  const estado = $("estado");
  estado.textContent = texto;
  estado.className = "estado " + clase;
}

function formatear(valor, decimales = 2) {
  if (valor === null || valor === undefined) return "—";
  return Number(valor).toLocaleString("es-PE",
    { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
}

/* ----- Paso principal: ejecutar la evaluación --------------------------- */
$("boton-evaluar").addEventListener("click", async () => {
  const archivo = $("archivo").files[0];
  if (!archivo) { mostrarEstado("Primero seleccione un archivo.", "error"); return; }

  const datos = new FormData();
  datos.append("archivo", archivo);
  datos.append("fraccion_prueba", $("fraccion").value);

  $("boton-evaluar").disabled = true;
  $("resultados").classList.add("oculto");
  mostrarEstado(
    "Evaluando los 5 modelos… Con una serie tarda menos de un minuto; " +
    "con un lote de 50 series puede tardar de 10 a 25 minutos por la búsqueda " +
    "de órdenes de ARIMA. No cierre esta ventana.",
    "cargando"
  );

  try {
    const respuesta = await fetch("/api/experimental/evaluar",
      { method: "POST", body: datos });
    const json = await respuesta.json();
    if (!respuesta.ok) throw new Error(json.error || "Error desconocido.");
    pintarResultados(json);
    mostrarEstado("Evaluación completada.", "exito");
  } catch (error) {
    mostrarEstado(error.message, "error");
  } finally {
    $("boton-evaluar").disabled = false;
  }
});

/* ----- Pintado de resultados --------------------------------------------- */
function pintarResultados(r) {
  $("resultados").classList.remove("oculto");
  pintarVeredicto(r);
  if (r.modo === "serie_unica") {
    pintarTablaSerie(r);
    graficoRealVsPredicho(r);
    graficoBarrasRmsse(r.tabla.map(f => ({ modelo: f.modelo, rmsse: f.rmsse })));
    $("panel-pruebas").classList.add("oculto");
    $("nota-omitidas").textContent = "";
  } else {
    pintarTablaLote(r);
    graficoBoxplot(r);
    graficoBarrasRmsse(r.resumen.map(f => ({ modelo: f.modelo, rmsse: f.rmsse_mediana })));
    pintarPruebas(r.pruebas);
    $("panel-pruebas").classList.remove("oculto");
    $("nota-omitidas").textContent = r.series_omitidas.length
      ? "Series omitidas por historial insuficiente: " + r.series_omitidas.join(" · ")
      : "";
  }
  $("descargar-evidencia").href = "/api/experimental/descargar/" + r.token_evidencia;
  $("panel-veredicto").scrollIntoView({ behavior: "smooth" });
}

function pintarVeredicto(r) {
  const esLote = r.modo === "lote";
  $("texto-ganador").textContent = r.ganador
    ? "Ganador: " + r.ganador
    : "Ningún modelo pudo evaluarse";
  $("texto-ganador-detalle").textContent = r.ganador
    ? (esLote
        ? `RMSSE mediano de ${formatear(r.ganador_rmsse)} sobre ${r.series_evaluadas} ` +
          `productos (RMSSE < 1 = mejor que el método ingenuo). Supera al método ` +
          `ingenuo en ${r.ganador_supera} de ${r.series_evaluadas} productos. ` +
          `Se usa la MEDIANA porque unas pocas series muy volátiles distorsionan el promedio.`
        : `RMSSE de ${formatear(r.ganador_rmsse)} sobre los últimos ${r.horizonte} días de ` +
          `"${r.serie}" (RMSSE < 1 = mejor que el método ingenuo). MAPE de referencia: ` +
          `${formatear(r.ganador_mape)} %.`)
    : "Revise que el archivo tenga suficiente historial.";
}

function celdaNumero(valor, decimales = 2) {
  return `<td class="numero">${formatear(valor, decimales)}</td>`;
}

function insigniaUmbral(cumple) {
  return cumple
    ? '<span class="insignia cumple">RMSSE &lt; 1</span>'
    : '<span class="insignia no-cumple">RMSSE ≥ 1</span>';
}

function pintarTablaSerie(r) {
  const filas = r.tabla.map(f => `
    <tr class="${f.ganador ? "fila-ganadora" : ""}">
      <td>${f.modelo} ${f.ganador ? '<span class="insignia ganador">GANADOR</span>' : ""}</td>
      ${f.error
        ? `<td colspan="6">Falló: ${f.error}</td><td>—</td>`
        : celdaNumero(f.rmsse) + celdaNumero(f.wape, 1) + celdaNumero(f.mae, 1) +
          celdaNumero(f.sesgo, 1) + celdaNumero(f.mape, 1) + celdaNumero(f.segundos, 3) +
          `<td>${insigniaUmbral(f.cumple_umbral)}</td>`}
    </tr>`).join("");
  $("tabla-metricas").innerHTML = `
    <thead><tr><th>Modelo</th><th>RMSSE ★</th><th>WAPE (%)</th><th>MAE (unid.)</th>
    <th>Sesgo (unid.)</th><th>MAPE (%)</th><th>Tiempo (s)</th><th>Veredicto</th></tr></thead>
    <tbody>${filas}</tbody>`;
}

function pintarTablaLote(r) {
  const filas = r.resumen.map(f => `
    <tr class="${f.ganador ? "fila-ganadora" : ""}">
      <td>${f.modelo} ${f.ganador ? '<span class="insignia ganador">GANADOR</span>' : ""}</td>
      ${celdaNumero(f.rmsse_mediana)}${celdaNumero(f.rmsse_promedio)}
      ${celdaNumero(f.wape_mediana, 1)}${celdaNumero(f.mae_promedio, 1)}
      ${celdaNumero(f.sesgo_promedio, 1)}
      <td class="numero">${f.series_supera_ingenuo} / ${f.series_evaluadas}</td>
      <td class="numero">${f.series_ganadas} / ${f.series_evaluadas}</td>
      <td>${insigniaUmbral(f.cumple_umbral)}</td>
    </tr>`).join("");
  $("tabla-metricas").innerHTML = `
    <thead><tr><th>Modelo</th><th>RMSSE mediano ★</th><th>RMSSE prom.</th><th>WAPE mediano (%)</th>
    <th>MAE prom.</th><th>Sesgo prom.</th><th>Supera ingenuo</th><th>Series ganadas</th>
    <th>Veredicto</th></tr></thead>
    <tbody>${filas}</tbody>`;
}

function pintarPruebas(pruebas) {
  if (!pruebas.length) {
    $("tabla-pruebas").innerHTML =
      "<tbody><tr><td>Se requieren al menos 5 series válidas para la inferencia.</td></tr></tbody>";
    return;
  }
  const filas = pruebas.map(p => `
    <tr>
      <td>${p.comparacion}</td>
      ${celdaNumero(p.p_valor_t, 4)}${celdaNumero(p.p_valor_wilcoxon, 4)}
      ${celdaNumero(p.d_cohen, 2)}<td>${p.interpretacion}</td>
      <td class="numero">${p.n}</td>
    </tr>`).join("");
  $("tabla-pruebas").innerHTML = `
    <thead><tr><th>Comparación (sobre RMSSE)</th><th>p-valor t pareada</th><th>p-valor Wilcoxon</th>
    <th>d de Cohen</th><th>Tamaño del efecto</th><th>N pares</th></tr></thead>
    <tbody>${filas}</tbody>`;
}

/* ----- Gráficos Plotly ------------------------------------------------------ */
const DISTRIBUCION_BASE = {
  font: { family: "Segoe UI, sans-serif", color: "#1C2530" },
  paper_bgcolor: "#FFFFFF",
  plot_bgcolor: "#FFFFFF",
  margin: { t: 50, r: 20, b: 60, l: 60 }
};

function graficoRealVsPredicho(r) {
  const trazas = [{
    x: r.fechas_prueba, y: r.valores_prueba, name: "Real (prueba)",
    mode: "lines+markers", line: { color: "#1C2530", width: 3 }
  }];
  for (const p of r.predicciones) {
    trazas.push({
      x: r.fechas_prueba, y: p.valores, name: p.modelo, mode: "lines",
      line: {
        color: COLORES[p.modelo] || "#999",
        width: p.modelo === r.ganador ? 3 : 1.6,
        dash: p.modelo === r.ganador ? "solid" : "dot"
      }
    });
  }
  Plotly.newPlot("grafico-principal", trazas, {
    ...DISTRIBUCION_BASE,
    title: `Real vs. predicho — últimos ${r.horizonte} días de "${r.serie}"`,
    xaxis: { title: "Fecha" }, yaxis: { title: "Unidades vendidas" }
  }, { responsive: true, displaylogo: false });
}

function graficoBoxplot(r) {
  // Cada caja resume la distribución de RMSSE de un modelo en las N series.
  const trazas = r.resumen.map(f => ({
    y: f.rmsses, name: f.modelo, type: "box", boxmean: true,
    marker: { color: f.ganador ? DORADO : (COLORES[f.modelo] || "#999") }
  }));
  Plotly.newPlot("grafico-principal", trazas, {
    ...DISTRIBUCION_BASE,
    title: `Distribución del RMSSE por modelo (${r.series_evaluadas} series)`,
    yaxis: { title: "RMSSE" },
    shapes: [{ // Línea de referencia: RMSSE = 1 (frontera del método ingenuo).
      type: "line", xref: "paper", x0: 0, x1: 1, y0: 1, y1: 1,
      line: { color: "#B3261E", dash: "dash", width: 1.5 }
    }],
    annotations: [{
      xref: "paper", x: 1, y: 1, text: "RMSSE = 1 (método ingenuo)",
      showarrow: false, yshift: 10, font: { color: "#B3261E", size: 11 }
    }]
  }, { responsive: true, displaylogo: false });
}

function graficoBarrasRmsse(filas) {
  const validas = filas.filter(f => f.rmsse !== null && f.rmsse !== undefined);
  const minimo = Math.min(...validas.map(f => f.rmsse));
  Plotly.newPlot("grafico-secundario", [{
    x: validas.map(f => f.modelo),
    y: validas.map(f => f.rmsse),
    type: "bar",
    text: validas.map(f => formatear(f.rmsse)),
    textposition: "outside",
    marker: { color: validas.map(f => f.rmsse === minimo ? DORADO : "#0E2A47") }
  }], {
    ...DISTRIBUCION_BASE,
    title: "RMSSE por modelo (menor es mejor; dorado = ganador)",
    yaxis: { title: "RMSSE" },
    shapes: [{
      type: "line", xref: "paper", x0: 0, x1: 1, y0: 1, y1: 1,
      line: { color: "#B3261E", dash: "dash", width: 1.5 }
    }]
  }, { responsive: true, displaylogo: false });
}
