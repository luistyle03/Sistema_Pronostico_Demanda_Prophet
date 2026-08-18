/* =====================================================================
   Módulo 2 (pronóstico retail) — Lógica del navegador.
   Flujo: cargar archivo -> elegir producto y parámetros -> generar ->
   pintar KPI, gráfico con banda de confianza, tabla diaria y descarga.
   ===================================================================== */
"use strict";

const $ = (id) => document.getElementById(id);
let tokenDatos = null;        // Identifica en el servidor el archivo cargado.
const feriados = [];          // [{fecha:'AAAA-MM-DD', nombre:'...'}]

function estado(id, texto, clase) {
  const e = $(id);
  e.textContent = texto;
  e.className = "estado " + clase;
}

function formatear(valor, decimales = 2) {
  if (valor === null || valor === undefined) return "—";
  return Number(valor).toLocaleString("es-PE",
    { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
}

function fechaLegible(iso) { // '2026-03-09' -> '09/03/2026'
  const [a, m, d] = iso.split("-");
  return `${d}/${m}/${a}`;
}

/* ----- Paso 1: cargar el archivo ----------------------------------------- */
$("boton-cargar").addEventListener("click", async () => {
  const archivo = $("archivo").files[0];
  if (!archivo) { estado("estado-carga", "Primero seleccione un archivo.", "error"); return; }
  const datos = new FormData();
  datos.append("archivo", archivo);
  estado("estado-carga", "Leyendo y validando el archivo…", "cargando");
  try {
    const respuesta = await fetch("/api/pronostico/cargar", { method: "POST", body: datos });
    const json = await respuesta.json();
    if (!respuesta.ok) throw new Error(json.error || "Error desconocido.");
    tokenDatos = json.token_datos;
    llenarProductos(json.elegibilidad);
    estado("estado-carga",
      `Archivo válido: ${json.filas} filas, del ${fechaLegible(json.fecha_inicio)} ` +
      `al ${fechaLegible(json.fecha_fin)}.`, "exito");
    $("panel-parametros").classList.remove("oculto");
    $("resultados").classList.add("oculto");
  } catch (error) {
    estado("estado-carga", error.message, "error");
  }
});

function llenarProductos(items) {
  const selector = $("producto");
  selector.innerHTML = "";
  if (items.length === 1 && items[0].agregado) {
    const p = items[0];
    const texto = p.elegible
      ? "Todos los productos (archivo sin columna producto)"
      : `Todos los productos — ${p.dias} días · NO elegible (mínimo 365)`;
    const opcion = new Option(texto, "");
    opcion.disabled = !p.elegible;
    selector.append(opcion);
    return;
  }

  selector.append(new Option("— Todos los productos (suma) —", ""));
  let primerElegible = null;
  for (const p of items) {
    const texto = p.elegible
      ? (p.dias ? `${p.nombre} (${p.dias} días)` : p.nombre)
      : `${p.nombre} — ${p.dias} días · NO elegible (mínimo 365)`;
    const opcion = new Option(texto, p.nombre);
    opcion.disabled = !p.elegible;            // RF03: un producto no elegible no se puede seleccionar.
    selector.append(opcion);
    if (p.elegible && primerElegible === null) primerElegible = p.nombre;
  }
  // Preselecciona el primer producto ELEGIBLE (si no hay ninguno, deja "— suma —").
  selector.value = primerElegible !== null ? primerElegible : "";
}

/* ----- Feriados personalizados --------------------------------------------- */
$("boton-feriado").addEventListener("click", () => {
  const fecha = $("feriado-fecha").value;
  const nombre = $("feriado-nombre").value.trim() || "Feriado del negocio";
  if (!fecha) return;
  feriados.push({ fecha, nombre });
  $("feriado-fecha").value = "";
  $("feriado-nombre").value = "";
  pintarFeriados();
});

function pintarFeriados() {
  $("lista-feriados").innerHTML = feriados.map((f, i) =>
    `<li>${fechaLegible(f.fecha)} · ${f.nombre}
       <button type="button" data-indice="${i}" title="Quitar">×</button></li>`).join("");
  // Botones de borrado: al hacer clic se quita ese feriado de la lista.
  $("lista-feriados").querySelectorAll("button").forEach(b =>
    b.addEventListener("click", () => { feriados.splice(Number(b.dataset.indice), 1); pintarFeriados(); }));
}

/* ----- Paso 2: generar el pronóstico ----------------------------------------- */
$("boton-generar").addEventListener("click", async () => {
  if (!tokenDatos) { estado("estado-generar", "Primero cargue un archivo.", "error"); return; }
  const cuerpo = {
    token_datos: tokenDatos,
    producto: $("producto").value,
    horizonte: Number($("horizonte").value),
    intervalo_confianza: Number($("intervalo").value),
    flexibilidad_tendencia: Number($("flexibilidad").value),
    estacionalidad_semanal: $("est-semanal").checked,
    estacionalidad_anual: $("est-anual").checked,
    estacionalidad_mensual: $("est-mensual").checked,
    pais_feriados: $("pais").value,
    feriados_personalizados: feriados
  };
  $("boton-generar").disabled = true;
  estado("estado-generar", "Entrenando Prophet y proyectando… (segundos)", "cargando");
  try {
    const respuesta = await fetch("/api/pronostico/generar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo)   // El objeto viaja como texto JSON.
    });
    const json = await respuesta.json();
    if (!respuesta.ok) throw new Error(json.error || "Error desconocido.");
    pintarResultados(json);
    estado("estado-generar", "Pronóstico generado.", "exito");
  } catch (error) {
    estado("estado-generar", error.message, "error");
  } finally {
    $("boton-generar").disabled = false;
  }
});

/* ----- Pintado de resultados --------------------------------------------------- */
function pintarResultados(r) {
  $("resultados").classList.remove("oculto");
  const resumen = r.resumen;
  $("kpi-total").textContent = formatear(resumen.total_proyectado, 0) + " uds.";
  $("kpi-variacion").textContent = resumen.variacion_porcentual === null
    ? "—"
    : (resumen.variacion_porcentual >= 0 ? "▲ +" : "▼ ") +
      formatear(resumen.variacion_porcentual, 1) + " %";
  $("kpi-pico").textContent =
    fechaLegible(resumen.fecha_pico) + " (" + formatear(resumen.valor_pico, 0) + ")";
  $("kpi-promedio").textContent = formatear(resumen.promedio_diario, 1) + " uds./día";

  graficoPronostico(r);
  graficoComponentes(r);
  pintarTabla(r);
  $("descargar-excel").href = "/api/pronostico/descargar/" + r.token_excel;
  $("hash-excel").textContent = r.sha256;
  $("resultados").scrollIntoView({ behavior: "smooth" });
}

function graficoPronostico(r) {
  const trazas = [];
  // 1) Banda de confianza: dos trazas; la segunda rellena hasta la primera.
  if (r.pronostico.superior.length) {
    trazas.push({
      x: r.pronostico.fechas, y: r.pronostico.superior,
      mode: "lines", line: { width: 0 }, hoverinfo: "skip",
      showlegend: false, name: "Límite superior"
    });
    trazas.push({
      x: r.pronostico.fechas, y: r.pronostico.inferior,
      mode: "lines", line: { width: 0 }, fill: "tonexty",
      fillcolor: "rgba(14, 42, 71, 0.14)",
      name: "Banda de confianza", hoverinfo: "skip"
    });
  }
  // 2) Historia real (gris) y 3) pronóstico (azul marino grueso).
  trazas.push({
    x: r.historia.fechas, y: r.historia.valores,
    mode: "lines", name: "Ventas históricas",
    line: { color: "#8A8F98", width: 1.4 }
  });
  trazas.push({
    x: r.pronostico.fechas, y: r.pronostico.valores,
    mode: "lines", name: "Pronóstico",
    line: { color: "#0E2A47", width: 3 }
  });
  Plotly.newPlot("grafico-pronostico", trazas, {
    font: { family: "Segoe UI, sans-serif", color: "#1C2530" },
    paper_bgcolor: "#FFFFFF", plot_bgcolor: "#FFFFFF",
    margin: { t: 50, r: 20, b: 60, l: 60 },
    title: `"${r.serie}" — historia y próximos ${r.horizonte} días`,
    xaxis: { title: "Fecha" },
    yaxis: { title: "Unidades vendidas" },
    legend: { orientation: "h", y: -0.25 },
    shapes: [{ // Línea vertical donde termina la historia y empieza el futuro.
      type: "line", x0: r.pronostico.fechas[0], x1: r.pronostico.fechas[0],
      yref: "paper", y0: 0, y1: 1,
      line: { color: "#D9A441", width: 1.5, dash: "dash" }
    }]
  }, { responsive: true, displaylogo: false });
}

/* ----- HU02: vista de descomposición ------------------------------------------
   Prophet es un modelo ADITIVO: pronóstico = tendencia + estacionalidades +
   feriados. Cada pieza se grafica por separado en una rejilla 2×2 para que el
   dueño VEA el porqué del número. Si el motor no ofrece descomposición
   (componentes = null), la sección completa se oculta. */
function graficoComponentes(r) {
  const seccion = $("seccion-componentes");
  const c = r.componentes;
  if (!c) { seccion.classList.add("oculto"); return; }
  seccion.classList.remove("oculto");

  const trazas = [];
  const notas = [];
  // Cuadrante 1 (arriba-izquierda): tendencia en el tiempo.
  trazas.push({
    x: c.tendencia.fechas, y: c.tendencia.valores,
    mode: "lines", name: "Tendencia",
    line: { color: "#0E2A47", width: 2.5 }, xaxis: "x", yaxis: "y"
  });
  // Cuadrante 2 (arriba-derecha): efecto de feriados en el tiempo.
  if (c.feriados) {
    trazas.push({
      x: c.feriados.fechas, y: c.feriados.valores,
      type: "bar", name: "Feriados",
      marker: { color: "#B4552D" }, xaxis: "x2", yaxis: "y2"
    });
  } else {
    notas.push("Sin componente de feriados: no se configuró calendario de país ni feriados propios.");
  }
  // Cuadrante 3 (abajo-izquierda): perfil semanal (lunes a domingo).
  if (c.semanal) {
    trazas.push({
      x: c.semanal.dias, y: c.semanal.valores,
      type: "bar", name: "Estacionalidad semanal",
      marker: { color: "#3D6B4F" }, xaxis: "x3", yaxis: "y3"
    });
  } else {
    notas.push("Estacionalidad semanal desactivada en los parámetros.");
  }
  // Cuadrante 4 (abajo-derecha): perfil anual (enero a diciembre).
  if (c.anual) {
    trazas.push({
      x: c.anual.dias, y: c.anual.valores,
      mode: "lines", name: "Estacionalidad anual",
      line: { color: "#7E3556", width: 2 }, xaxis: "x4", yaxis: "y4"
    });
  } else {
    notas.push("Estacionalidad anual desactivada en los parámetros.");
  }

  const tituloEje = (texto) => ({ title: { text: texto, font: { size: 11 } } });
  Plotly.newPlot("grafico-componentes", trazas, {
    grid: { rows: 2, columns: 2, pattern: "independent" },
    height: 560,
    font: { family: "Segoe UI, sans-serif", color: "#1C2530" },
    paper_bgcolor: "#FFFFFF", plot_bgcolor: "#FFFFFF",
    margin: { t: 60, r: 20, b: 60, l: 60 },
    title: "Descomposición del pronóstico: pronóstico = tendencia + estacionalidades + feriados",
    showlegend: false,
    xaxis:  tituloEje("Tendencia"),
    xaxis2: tituloEje("Efecto de feriados"),
    xaxis3: tituloEje("Perfil semanal"),
    xaxis4: Object.assign(tituloEje("Perfil anual (día del año)"), {
      // 365 etiquetas 'MM-DD': se muestran solo los inicios de mes.
      tickvals: ["01-01", "02-01", "03-01", "04-01", "05-01", "06-01",
                 "07-01", "08-01", "09-01", "10-01", "11-01", "12-01"],
      ticktext: ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                 "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]
    }),
    yaxis:  { title: "uds." }, yaxis2: { title: "uds." },
    yaxis3: { title: "uds." }, yaxis4: { title: "uds." }
  }, { responsive: true, displaylogo: false });

  const nota = $("nota-componentes");
  if (notas.length) { nota.textContent = notas.join(" "); nota.classList.remove("oculto"); }
  else { nota.textContent = ""; nota.classList.add("oculto"); }
}

function pintarTabla(r) {
  const hayBanda = r.pronostico.inferior.length > 0;
  const filas = r.pronostico.fechas.map((f, i) => `
    <tr>
      <td>${fechaLegible(f)}</td>
      <td class="numero">${formatear(r.pronostico.valores[i])}</td>
      ${hayBanda
        ? `<td class="numero">${formatear(r.pronostico.inferior[i])}</td>
           <td class="numero">${formatear(r.pronostico.superior[i])}</td>`
        : ""}
    </tr>`).join("");
  $("tabla-pronostico").innerHTML = `
    <thead><tr><th>Fecha</th><th>Pronóstico (uds.)</th>
    ${hayBanda ? "<th>Límite inferior</th><th>Límite superior</th>" : ""}</tr></thead>
    <tbody>${filas}</tbody>`;
}
