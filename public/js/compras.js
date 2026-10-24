// app-purchase · W-PURCHASE-01 (órdenes de compra): bandeja, filtros, tabla, acciones en lote, detalle con la
// explicación de cada cantidad sugerida, aprobación por monto y envío al proveedor con PIN u OTP.
import { accion, store } from "./app.js";
import { api } from "./api.js";
import { abrirDrawer, abrirModal, cerrarDrawer, conPunto, drawerAbierto, esc, fechaCorta, fechaHora, icono, soles, toast } from "./ui.js";

const CLASE_ESTADO = { BORRADOR: "", PENDIENTE_APROBACION: "ambar", APROBADA: "verde", RECIBIDA_PARCIAL: "azul", RECIBIDA: "", ANULADA: "rojo" };
const ABIERTAS = ["BORRADOR", "PENDIENTE_APROBACION", "APROBADA", "RECIBIDA_PARCIAL"];

export function vistaCompras(raiz) {
  const f = { chip: "abiertas", tarjeta: null, texto: "", marcadas: new Set() };
  leerRuta(location.hash);

  function leerRuta(hash) {
    const q = new URLSearchParams(hash.split("?")[1] || "");
    if (q.get("origen") === "IA") f.tarjeta = "ia";
    else if (!hash.includes("/OC-")) f.tarjeta = null;
  }

  raiz.innerHTML = `<div class="pestanas"><button class="chip" aria-pressed="true">Órdenes</button>
      <button class="chip" disabled title="Fuera de esta demo (W-PURCHASE-06)">Requerimientos</button>
      <button class="chip" disabled title="Fuera de esta demo (W-PURCHASE-07)">Cuentas por pagar</button></div>
    <h1>Órdenes de compra</h1><p class="sub">Lo que pediste a tus proveedores: qué falta aprobar, qué falta enviar y qué falta recibir.</p>
    <div id="c-cuerpo"><div class="bandeja" style="margin-top:24px">${'<div class="kpi esqueleto" style="height:96px"></div>'.repeat(4)}</div>
    <div class="caja esqueleto" style="height:420px"></div></div>`;
  const cuerpo = raiz.querySelector("#c-cuerpo");

  function filtradas(e) {
    let l = e.ocs;
    if (f.chip === "abiertas") l = l.filter((o) => ABIERTAS.includes(o.estado));
    if (f.chip === "recibidas") l = l.filter((o) => o.estado === "RECIBIDA");
    if (f.tarjeta === "por_aprobar") l = l.filter((o) => o.estado === "PENDIENTE_APROBACION");
    if (f.tarjeta === "por_enviar") l = l.filter((o) => o.estado === "APROBADA" && !o.enviada_al_proveedor);
    if (f.tarjeta === "por_recibir") l = l.filter((o) => o.por_recibir && o.enviada_al_proveedor).sort((a, b) => (b.atraso_dias || 0) - (a.atraso_dias || 0));
    if (f.tarjeta === "ia") l = l.filter((o) => o.origen === "AGENTE");
    if (f.texto) { const t = f.texto.toLowerCase(); l = l.filter((o) => `${o.numero} ${o.proveedor || "sin proveedor"}`.toLowerCase().includes(t)); }
    return l;
  }

  function accionesFila(o) {
    const a = o.acciones;
    const enlaces = [];
    if (o.estado === "BORRADOR") enlaces.push(`<button class="enlace" data-abrir="${o.numero}">${o.origen === "AGENTE" ? "Revisar" : "Editar"} ›</button>`);
    if (o.estado === "PENDIENTE_APROBACION") enlaces.push(a.aprobar?.permitido ? `<button class="enlace" data-abrir="${o.numero}">Revisar ›</button>`
      : `<button class="enlace" data-abrir="${o.numero}">Ver ›</button><small>${esc(a.aprobar?.motivo || "")}</small>`);
    if (o.estado === "APROBADA" && !o.enviada_al_proveedor) enlaces.push(`<button class="enlace" data-enviar="${o.numero}" ${a.enviar_proveedor?.permitido ? "" : "disabled"} title="${esc(a.enviar_proveedor?.motivo || "Exige el PIN del Administrador")}">Enviar al proveedor ›</button>`);
    if (o.enviada_al_proveedor && ["APROBADA", "RECIBIDA_PARCIAL"].includes(o.estado)) enlaces.push(`<button class="enlace" disabled title="${esc(a.recibir?.motivo || "")}">${o.estado === "RECIBIDA_PARCIAL" ? "Recibir el resto" : "Recibir"} ›</button>`);
    if (!enlaces.length) enlaces.push(`<button class="enlace" data-abrir="${o.numero}">Ver ›</button>`);
    return `<div class="acciones-fila">${enlaces.join("")}</div>`;
  }

  function fila(o, verCostos) {
    const marcable = ["BORRADOR", "PENDIENTE_APROBACION"].includes(o.estado);
    const entrega = o.fecha_entrega ? `${fechaCorta(o.fecha_entrega)}${o.atraso_dias ? `<small style="color:var(--ambar)">Atrasada · ${o.atraso_dias} día${o.atraso_dias > 1 ? "s" : ""}</small>` : ""}` : "—";
    const enviada = o.enviada_al_proveedor ? `<small>Enviada ${esc(fechaCorta(o.enviada_al_proveedor.ts))}</small>` : "";
    const creada = o.origen === "AGENTE" ? `hoy ${fechaHora(o.creada_en).split("· ")[1]} · agente` : `${fechaCorta(o.creada_en)} · ${esc(o.creada_por)}`;
    return `<tr class="clic ${f.marcadas.has(o.numero) ? "marcada" : ""}" data-fila="${o.numero}">
      <td data-col="sel">${marcable ? `<input type="checkbox" data-marcar="${o.numero}" ${f.marcadas.has(o.numero) ? "checked" : ""} aria-label="Marcar ${o.numero}">` : ""}</td>
      <td data-col="orden">${o.origen === "AGENTE" ? `<span class="badge ia" style="margin-bottom:4px">Generada por IA</span><br>` : ""}<b>${esc(o.numero)}</b><small>${o.origen === "AGENTE" ? esc(fechaHora(o.creada_en)) + " · agente" : creada}</small></td>
      <td data-col="Proveedor">${o.proveedor ? esc(o.proveedor) : `<span class="tenue">Sin proveedor</span>`}<small>${o.proveedor ? esc(o.condicion_pago || "") : `${o.n_lineas} producto${o.n_lineas > 1 ? "s" : ""} sin compras previas`}</small></td>
      <td data-col="Estado"><span class="badge ${CLASE_ESTADO[o.estado]}">${esc(o.estado_etiqueta)}</span>${enviada}</td>
      <td data-col="Entrega" class="ocultable">${entrega}</td>
      <td data-col="Monto" class="nw">${verCostos ? (o.monto == null ? `—<small>falta el costo</small>` : `${soles(o.monto)}${o.monto_estimado ? "<small>incompleto</small>" : ""}`) : "—"}</td>
      <td data-col="Por recibir" class="ocultable nw">${o.por_recibir ? (o.recibidas ? `${o.recibidas} de ${o.recibidas + o.por_recibir} u.` : `${o.por_recibir} u.`) : o.estado === "BORRADOR" || o.estado === "PENDIENTE_APROBACION" ? `${o.n_lineas} producto${o.n_lineas > 1 ? "s" : ""}` : "—"}</td>
      <td data-col="Acciones">${accionesFila(o)}</td></tr>`;
  }

  function barraLote(e) {
    const sel = e.ocs.filter((o) => f.marcadas.has(o.numero));
    if (!sel.length) return "";
    const borradores = sel.filter((o) => o.estado === "BORRADOR");
    const enviables = borradores.filter((o) => o.acciones.enviar_aprobacion?.permitido);
    const pendientes = sel.filter((o) => o.estado === "PENDIENTE_APROBACION");
    const total = sel.reduce((s, o) => s + (o.monto || 0), 0);
    return `<div class="barra-lote" role="region" aria-label="Acciones en lote"><span>${sel.length} marcada${sel.length > 1 ? "s" : ""}${e.usuario.puede["costos.ver"] ? ` · ${soles(total)}` : ""}</span>
      <button class="boton fantasma chico" data-quitar>Quitar selección</button>
      ${borradores.length ? `<button class="boton chico primario" data-enviar-lote ${enviables.length ? "" : "disabled"}>Enviar ${enviables.length} a aprobación</button>` : ""}
      ${pendientes.length ? `<button class="boton chico primario" data-aprobar-lote>Aprobar…</button>` : ""}</div>`;
  }

  function pintar(e) {
    if (!e.usuario.puede["compras.ver"]) {
      cuerpo.innerHTML = `<div class="caja bloqueo"><div class="icono-grande">${icono("candado", 26)}</div><h2>No tienes acceso a Compras</h2>
        <p class="sub" style="margin:8px auto 0">Tu rol (${esc(e.usuario.rol)}) no incluye órdenes de compra. Cambia de usuario en la cabecera para ver esta pantalla.</p></div>`;
      return;
    }
    const k = e.kpis, verCostos = e.usuario.puede["costos.ver"];
    const abiertas = e.ocs.filter((o) => ABIERTAS.includes(o.estado)).length;
    const lista = filtradas(e);
    const tarjeta = (id, titulo, valor, detalle, clase = "") => `<button class="kpi ${clase}" data-tarjeta="${id}" aria-pressed="${f.tarjeta === id}"><small>${titulo}</small><b>${valor}</b><span>${detalle}</span></button>`;
    const sucursal = e.usuario.sucursales.length > 1 ? "Todas tus sucursales" : e.usuario.sucursales[0] || "—";
    const ultimaIA = e.ocs.find((o) => o.origen === "AGENTE");
    cuerpo.innerHTML = `<div class="revisando"><span class="avatar">${esc(sucursal.slice(0, 1))}</span><div style="flex:1"><small>Estás revisando</small><b>${esc(sucursal)}</b>
        <span class="tenue peq">${abiertas} órdenes abiertas${k.generadas_ia.borradores ? ` · ${k.generadas_ia.borradores} borrador${k.generadas_ia.borradores > 1 ? "es" : ""} los dejó el agente${ultimaIA ? " el " + esc(fechaHora(ultimaIA.creada_en)) : ""}` : ""}</span></div>
        <a class="boton chico" href="#/ia">${icono("ia", 16)}Asistente IA</a></div>
      <div class="bandeja">
        ${tarjeta("por_aprobar", "Por aprobar", `${k.por_aprobar.n} orden${k.por_aprobar.n === 1 ? "" : "es"}`, verCostos ? `${soles(k.por_aprobar.monto)} · tope ${soles(e.config.tope_aprobacion)}` : `tope de aprobación por monto`)}
        ${tarjeta("por_enviar", "Por enviar", `${k.por_enviar.n} orden${k.por_enviar.n === 1 ? "" : "es"}`, "aprobadas · necesitan tu PIN")}
        ${tarjeta("por_recibir", "Por recibir", `${k.por_recibir.n} orden${k.por_recibir.n === 1 ? "" : "es"}`, k.por_recibir.atrasadas ? `${k.por_recibir.atrasadas} atrasada${k.por_recibir.atrasadas > 1 ? "s" : ""}` : "ninguna atrasada")}
        ${tarjeta("ia", "Generadas por IA", `${k.generadas_ia.n} por revisar`, `${k.generadas_ia.borradores} borrador${k.generadas_ia.borradores === 1 ? "" : "es"} del agente`, "ia")}</div>
      <div class="herramientas">
        ${[["abiertas", `Abiertas · ${abiertas}`], ["recibidas", "Recibidas"], ["todas", "Todas"]].map(([id, t]) => `<button class="chip" data-chip="${id}" aria-pressed="${f.chip === id}">${t}</button>`).join("")}
        ${f.tarjeta ? `<button class="chip" data-limpiar-tarjeta aria-pressed="true">${{ por_aprobar: "Por aprobar", por_enviar: "Por enviar", por_recibir: "Por recibir", ia: "Origen: Generada por IA" }[f.tarjeta]} · ${lista.length} <span class="x">×</span></button>` : ""}
        <input class="campo" type="search" id="c-buscar" placeholder="Buscar por número o proveedor…" value="${esc(f.texto)}" aria-label="Buscar órdenes">
        <button class="boton primario" disabled title="El formulario de orden (W-PURCHASE-02) está fuera de esta demo">+ Nueva orden</button></div>
      <p class="ayuda">La más reciente arriba. Marca borradores para enviarlos a aprobación, o pendientes para aprobarlos.</p>
      <div class="caja tabla-caja"><table class="tabla apilable"><thead><tr><th style="width:36px"></th><th>Orden<small>número · fecha</small></th><th>Proveedor<small>condición de pago</small></th>
        <th>Estado<small>dónde va</small></th><th class="ocultable">Entrega<small>estimada</small></th><th>Monto<small>total con IGV</small></th><th class="ocultable">Por recibir<small>saldo</small></th><th>Acciones<small>en esta fila</small></th></tr></thead>
        <tbody>${lista.length ? lista.map((o) => fila(o, verCostos)).join("") : `<tr><td colspan="8" style="text-align:center;padding:40px" class="tenue">No hay órdenes con este filtro.</td></tr>`}</tbody></table></div>
      ${barraLote(e)}`;
    enlazar(e);
  }

  function enlazar(e) {
    cuerpo.querySelectorAll("[data-tarjeta]").forEach((b) => b.addEventListener("click", () => { f.tarjeta = f.tarjeta === b.dataset.tarjeta ? null : b.dataset.tarjeta; f.chip = "abiertas"; pintar(e); }));
    cuerpo.querySelectorAll("[data-chip]").forEach((b) => b.addEventListener("click", () => { f.chip = b.dataset.chip; pintar(e); }));
    cuerpo.querySelector("[data-limpiar-tarjeta]")?.addEventListener("click", () => { f.tarjeta = null; history.replaceState(null, "", "#/compras"); pintar(e); });
    const buscar = cuerpo.querySelector("#c-buscar");
    buscar.addEventListener("input", () => { f.texto = buscar.value; const pos = buscar.selectionStart; pintar(e); const n = cuerpo.querySelector("#c-buscar"); n.focus(); n.setSelectionRange(pos, pos); });
    cuerpo.querySelectorAll("[data-marcar]").forEach((c) => c.addEventListener("click", (ev) => { ev.stopPropagation(); c.checked ? f.marcadas.add(c.dataset.marcar) : f.marcadas.delete(c.dataset.marcar); pintar(e); }));
    cuerpo.querySelectorAll("[data-fila]").forEach((tr) => tr.addEventListener("click", (ev) => { if (!ev.target.closest("button, input, a")) location.hash = `#/compras/${tr.dataset.fila}`; }));
    cuerpo.querySelectorAll("[data-abrir]").forEach((b) => b.addEventListener("click", () => (location.hash = `#/compras/${b.dataset.abrir}`)));
    cuerpo.querySelectorAll("[data-enviar]").forEach((b) => b.addEventListener("click", () => pedirPin(b.dataset.enviar)));
    cuerpo.querySelector("[data-quitar]")?.addEventListener("click", () => { f.marcadas.clear(); pintar(e); });
    cuerpo.querySelector("[data-enviar-lote]")?.addEventListener("click", async () => {
      const numeros = e.ocs.filter((o) => f.marcadas.has(o.numero) && o.estado === "BORRADOR").map((o) => o.numero);
      await enviarAAprobacion(numeros); f.marcadas.clear(); pintar(store.estado);
    });
    cuerpo.querySelector("[data-aprobar-lote]")?.addEventListener("click", () => revisarAntesDeAprobar(e.ocs.filter((o) => f.marcadas.has(o.numero) && o.estado === "PENDIENTE_APROBACION"), () => f.marcadas.clear()));
  }

  if (store.estado) pintar(store.estado);
  return {
    actualizar: pintar,
    ruta: (hash) => { leerRuta(hash); if (!hash.includes("/OC-")) cerrarDrawer(); if (store.estado) pintar(store.estado); },
    destruir: () => cerrarDrawer(),
  };
}

// ── Enviar a aprobación (01h → 01i) ─────────────────────────
async function enviarAAprobacion(numeros) {
  const r = await accion("POST", "/api/compras/enviar-aprobacion", { numeros });
  const res = r.resultado;
  const partes = [];
  if (res.pendientes.length) partes.push(`Enviaste ${res.pendientes.map((p) => p.numero).join(", ")} a aprobación: supera${res.pendientes.length > 1 ? "n" : ""} el tope de ${soles(res.tope)}`);
  if (res.aprobadas.length) partes.push(`${res.aprobadas.map((p) => p.numero).join(", ")} quedó aprobada${res.aprobadas.length > 1 ? "s" : ""} por estar bajo el tope`);
  if (partes.length) toast(partes.join(". ") + ".", res.pendientes.length === 1 ? { accion: "Ver", onAccion: () => (location.hash = `#/compras/${res.pendientes[0].numero}`) } : {});
  if (res.omitidas.length) toast(res.omitidas.map((p) => `${p.numero} no se envió: ${p.motivo.charAt(0).toLowerCase() + p.motivo.slice(1)}`).join(". ") + ".", { error: true });
  return res;
}

// ── Revisa antes de aprobar (01f) y aviso con Deshacer (01g) ─
function revisarAntesDeAprobar(ordenes, alTerminar) {
  const uid = store.estado.usuario.id;
  const incluidas = ordenes.filter((o) => o.acciones.aprobar?.permitido);
  const excluidas = ordenes.filter((o) => !o.acciones.aprobar?.permitido);
  const total = incluidas.reduce((s, o) => s + (o.monto || 0), 0);
  const d = abrirDrawer({
    cabecera: `<h2>Revisa antes de aprobar</h2><p class="sub peq">Se aprobarán ${incluidas.length} orden${incluidas.length === 1 ? "" : "es"} por ${soles(total)}.</p>`,
    cuerpo: `${incluidas.map((o) => `<div class="dato"><span>${o.origen === "AGENTE" ? '<span class="badge ia">IA</span> ' : ""}${esc(o.numero)} · ${esc(o.proveedor)}</span><b>${soles(o.monto)}</b></div>`).join("")}
      ${excluidas.length ? `<h3 class="seccion-titulo">Quedan fuera</h3>${excluidas.map((o) => `<div class="dato"><span>${esc(o.numero)}</span><span>${esc(o.acciones.aprobar?.motivo || "")}</span></div>`).join("")}` : ""}
      <p class="ayuda" style="margin-top:16px">Las órdenes del agente sí se pueden aprobar: no tienen un creador humano. Enviarlas al proveedor seguirá exigiendo el PIN.</p>`,
    pie: `<button class="boton" data-cancelar>Cancelar</button><button class="boton primario" data-ok ${incluidas.length ? "" : "disabled"}>Aprobar ${incluidas.length} orden${incluidas.length === 1 ? "" : "es"}</button>`,
  });
  d.querySelector("[data-cancelar]").addEventListener("click", cerrarDrawer);
  d.querySelector("[data-ok]").addEventListener("click", async () => {
    const numeros = incluidas.map((o) => o.numero);
    await accion("POST", "/api/compras/aprobar", { numeros });
    cerrarDrawer(); alTerminar && alTerminar();
    toast(`Aprobaste ${numeros.join(", ")}.`, { accion: "Deshacer", onAccion: () => accion("POST", "/api/compras/deshacer", { numeros }).then(() => toast("Aprobación deshecha.")) });
  });
  void uid;
}

// ── Regla de reposición: por qué el agente sugirió esa cantidad ─
function reglaReposicion(l) {
  const d = l.detalle;
  if (!d) return "";
  const cobertura = Math.ceil(d.velocidad_diaria * d.dias_cobertura);
  const total = Math.max(d.stock_disponible + d.en_transito + l.cantidad, d.stock_minimo, cobertura, 1) * 1.08;
  const pct = (v) => `${(v / total) * 100}%`;
  return `<div class="regla-repo"><div class="regla-barra" role="img" aria-label="Stock ${d.stock_disponible}, en camino ${d.en_transito}, este pedido ${l.cantidad}, mínimo ${d.stock_minimo}, cobertura ${cobertura}">
      <span class="seg stock" style="width:${pct(d.stock_disponible)}">${d.stock_disponible || ""}</span>
      ${d.en_transito ? `<span class="seg transito" style="width:${pct(d.en_transito)}">${d.en_transito}</span>` : ""}
      <span class="seg pedido" style="width:${pct(l.cantidad)}">${l.cantidad}</span>
      <span class="regla-marca minimo" style="left:${pct(d.stock_minimo)}" title="Mínimo ${d.stock_minimo}"></span>
      <span class="regla-marca" style="left:${pct(cobertura)}" title="Cobertura de ${d.dias_cobertura} días: ${cobertura}"></span></div>
    <div class="regla-leyenda"><span><i style="background:var(--tarjeta-2);box-shadow:inset 0 0 0 1px var(--linea)"></i>Stock ${d.stock_disponible}</span>
      ${d.en_transito ? `<span><i style="background:var(--azul-fondo)"></i>En camino ${d.en_transito}</span>` : ""}
      <span><i style="background:var(--acento)"></i>Este pedido ${l.cantidad}</span><span><i style="background:var(--ambar)"></i>Mínimo ${d.stock_minimo}</span>
      <span><i style="background:var(--texto)"></i>Cobertura ${d.dias_cobertura} días ≈ ${cobertura}</span></div>
    <div class="regla-pasos"><span>Vendes <b>${d.velocidad_diaria}</b> por día (${d.vendidas_en_ventana} en ${d.ventana_dias} días).</span>
      <span>Para cubrir ${d.dias_cobertura} días te faltan <b>${d.reposicion_analytics}</b>; para volver al mínimo, <b>${d.faltante_al_minimo}</b>. Se toma la mayor: <b>${d.necesidad}</b>.</span>
      ${d.en_transito ? `<span>Ya vienen <b>${d.en_transito}</b> en camino (${esc(d.oc_en_transito.join(", "))}): quedan <b>${d.cantidad_sugerida}</b>.</span>` : ""}
      <span class="tenue">Es una cantidad sugerida que puedes editar, no un lote económico.</span></div></div>`;
}

// ── Detalle de la orden (drawer) ────────────────────────────
export async function abrirOrden(numero) {
  let o;
  try { o = await api("GET", `/api/compras/${numero}`); }
  catch (e) { toast(e.message, { error: true }); history.replaceState(null, "", "#/compras"); return; }
  pintarOrden(o);
}

function pintarOrden(o) {
  const previo = drawerAbierto();
  const scroll = previo?.dataset.oc === o.numero ? previo.querySelector(".drawer-cuerpo").scrollTop : 0;
  const abiertos = previo?.dataset.oc === o.numero ? [...previo.querySelectorAll("details")].map((x) => x.open) : null;
  const a = o.acciones;
  const editable = a.editar?.permitido;
  const corrida = o.origen === "AGENTE" ? o.historial[0] : null;
  const cab = `<div class="fila" style="gap:8px;margin-bottom:6px">${o.origen === "AGENTE" ? '<span class="badge ia">Generada por IA</span>' : ""}<span class="badge ${CLASE_ESTADO[o.estado]}">${esc(o.estado_etiqueta)}</span></div>
    <h2 style="font-size:22px">${esc(o.numero)}</h2><p class="sub peq">${o.proveedor ? `${esc(o.proveedor)} · ${esc(o.condicion_pago || "")}` : "Sin proveedor asignado"}${o.fecha_entrega ? ` · entrega estimada ${esc(fechaCorta(o.fecha_entrega))}` : ""}</p>`;
  const proveedor = editable ? `<label class="peq tenue" for="sel-prov">Proveedor</label>
    <select class="campo" id="sel-prov" style="width:100%;margin:6px 0 18px">${o.proveedor_id ? "" : '<option value="">Elige un proveedor…</option>'}${o.proveedores.map((p) => `<option value="${esc(p.id)}" ${p.id === o.proveedor_id ? "selected" : ""}>${esc(p.nombre)}</option>`).join("")}</select>` : "";
  const lineas = o.lineas.map((l, i) => `<div class="linea-oc"><div class="linea-oc-cab"><div class="nombre"><b>${esc(l.producto)} — ${esc(l.variante)}</b>
      <small>${esc(l.sku)} · para ${esc(l.almacen)}${l.stock_actual != null ? ` · stock hoy ${l.stock_actual}` : ""}</small>
      ${l.sugerida && l.cantidad !== l.sugerida ? `<span class="editada">Editada: el agente sugirió ${l.sugerida}</span>` : ""}</div>
      <div style="text-align:right">${editable ? `<div class="cantidad"><input type="number" min="1" max="9999" value="${l.cantidad}" data-cant="${i}" aria-label="Cantidad de ${esc(l.sku)}"><span class="tenue peq">u.</span></div>`
        : `<b>${l.cantidad} u.</b>${l.recibida ? `<small class="tenue" style="display:block">${l.recibida} recibidas</small>` : ""}`}
        ${o.puede_ver_costos ? (l.costo_unitario == null && editable ? `<div class="cantidad" style="margin-top:6px"><span class="tenue peq">S/</span><input type="number" step="0.01" min="0.01" placeholder="costo" data-costo="${i}" aria-label="Costo unitario de ${esc(l.sku)}"></div>`
          : `<small class="tenue" style="display:block;margin-top:4px">${soles(l.costo_unitario)} c/u · ${soles(l.subtotal)}</small>`) : ""}</div></div>
      ${l.detalle ? `<details ${i === 0 && o.estado === "BORRADOR" ? "open" : ""}><summary class="enlace peq" style="margin-top:10px;cursor:pointer">¿Por qué ${l.sugerida}?</summary>${reglaReposicion(l)}</details>` : ""}
      ${editable && o.lineas.length > 1 ? `<button class="enlace peq" data-quitar-linea="${i}" style="margin-top:10px;color:var(--texto-3)">Quitar de la orden</button>` : ""}</div>`).join("");
  const tope = o.tope_aprobacion;
  const notaTope = o.estado === "BORRADOR" && o.monto != null && tope ? `<div class="aviso ${o.monto > tope ? "ambar" : ""}" style="margin-top:4px">${icono("info")}<div>Tope de aprobación por monto: ${soles(tope)}. Al enviarla, esta orden ${o.monto > tope ? "quedará <b>Pendiente de aprobación</b>" : "pasará directo a <b>Aprobada</b>"}.</div></div>` : "";
  const total = o.puede_ver_costos ? `<div class="dato" style="font-size:16px;margin:8px 0 12px"><span>Total${o.monto_estimado ? " (incompleto: faltan costos)" : ""}</span><b>${soles(o.monto)}</b></div>` : "";
  const tiempo = `<h3 class="seccion-titulo">Historial</h3><ol class="linea-tiempo">${o.historial.map((h) => `<li class="${String(h.actor).startsWith("agente") ? "agente" : /PIN|OTP/.test(h.accion) ? "pin" : ""}">
      <b>${esc(h.accion)}</b><small>${esc(h.actor_nombre)} · ${esc(fechaHora(h.ts))}${h.detalle ? ` · ${esc(h.detalle)}` : ""}</small></li>`).join("")}</ol>`;
  const aviso = corrida ? `<div class="aviso" style="margin-bottom:18px">${icono("ia")}<div>La propuso el Agente de Abastecimiento el ${esc(fechaHora(corrida.ts))}. Las cantidades son sugeridas: revísalas antes de enviarla. El badge «Generada por IA» no cambia ningún paso.</div></div>` : "";
  const enviada = o.enviada_al_proveedor ? `<div class="aviso" style="margin-bottom:18px;background:var(--verde-fondo)">${icono("enviar")}<div>Enviada al proveedor por ${o.enviada_al_proveedor.canal === "whatsapp" ? "WhatsApp" : "correo"} el ${esc(fechaHora(o.enviada_al_proveedor.ts))}${o.enviada_al_proveedor.autorizacion ? `, autorizada con ${esc(o.enviada_al_proveedor.autorizacion)}` : ""}.</div></div>` : "";

  const btn = (clave, texto, clase, attr) => { const x = a[clave]; return x ? `<button class="boton ${clase}" ${attr} ${x.permitido ? "" : "disabled"} title="${esc(x.motivo || "")}">${texto}</button>` : ""; };
  const motivo = Object.values(a).find((x) => !x.permitido)?.motivo;
  const pie = [motivo ? `<span class="tenue peq" style="margin-right:auto">${esc(motivo)}</span>` : "",
    btn("deshacer_aprobacion", "Deshacer aprobación", "fantasma", "data-deshacer"),
    btn("rechazar", "Rechazar", "", "data-rechazar"), btn("aprobar", "Aprobar", "primario", "data-aprobar"),
    btn("enviar_aprobacion", "Enviar a aprobación", "primario", "data-enviar-aprob"),
    btn("enviar_proveedor", `${icono("candado", 16)}Enviar al proveedor`, "primario", "data-pin"),
    a.recibir ? `<button class="boton" disabled title="${esc(a.recibir.motivo)}">Recibir ›</button>` : ""].join("");

  const d = abrirDrawer({ ancho: true, cabecera: cab, cuerpo: aviso + enviada + proveedor + lineas + total + notaTope + tiempo, pie,
    alCerrar: () => { if (location.hash.includes("/OC-")) history.replaceState(null, "", "#/compras"); } });

  d.dataset.oc = o.numero;
  d.querySelector(".drawer-cuerpo").scrollTop = scroll;
  if (abiertos) d.querySelectorAll("details").forEach((x, i) => { x.open = !!abiertos[i]; });
  const actualizar = async (ruta, cuerpo) => { try { const r = await api("POST", ruta, cuerpo); pintarOrden(r); } catch (e) { toast(e.message, { error: true }); } };
  d.querySelector("#sel-prov")?.addEventListener("change", (ev) => ev.target.value && actualizar(`/api/compras/${o.numero}/proveedor`, { proveedor_id: ev.target.value }));
  d.querySelectorAll("[data-cant]").forEach((inp) => inp.addEventListener("change", () => {
    const l = o.lineas[inp.dataset.cant];
    actualizar(`/api/compras/${o.numero}/linea`, { sku: l.sku, almacen_id: l.almacen_id, cantidad: Number(inp.value) });
  }));
  d.querySelectorAll("[data-costo]").forEach((inp) => inp.addEventListener("change", () => {
    const l = o.lineas[inp.dataset.costo];
    actualizar(`/api/compras/${o.numero}/linea`, { sku: l.sku, almacen_id: l.almacen_id, costo_unitario: Number(inp.value) });
  }));
  d.querySelectorAll("[data-quitar-linea]").forEach((b) => b.addEventListener("click", () => {
    const l = o.lineas[b.dataset.quitarLinea];
    actualizar(`/api/compras/${o.numero}/linea`, { sku: l.sku, almacen_id: l.almacen_id, quitar: true });
  }));
  d.querySelector("[data-enviar-aprob]")?.addEventListener("click", async () => { await enviarAAprobacion([o.numero]); abrirOrden(o.numero); });
  d.querySelector("[data-aprobar]")?.addEventListener("click", async () => {
    await accion("POST", "/api/compras/aprobar", { numeros: [o.numero] });
    toast(`Aprobaste ${o.numero}. Ya puedes enviarla al proveedor.`, { accion: "Deshacer", onAccion: () => accion("POST", "/api/compras/deshacer", { numeros: [o.numero] }) });
    abrirOrden(o.numero);
  });
  d.querySelector("[data-rechazar]")?.addEventListener("click", async () => { await accion("POST", `/api/compras/${o.numero}/rechazar`, {}); toast(`${o.numero} volvió a Borrador.`); abrirOrden(o.numero); });
  d.querySelector("[data-deshacer]")?.addEventListener("click", async () => { await accion("POST", "/api/compras/deshacer", { numeros: [o.numero] }); abrirOrden(o.numero); });
  d.querySelector("[data-pin]")?.addEventListener("click", () => pedirPin(o.numero, o));
  // cualquier cambio en el drawer refresca también la tabla
  if (store.estado) api("GET", "/api/estado").then((e) => import("./app.js").then((m) => m.setEstado(e))).catch(() => {});
}

// ── Gate de PIN (único modal permitido) con OTP de contingencia ─
async function pedirPin(numero, orden) {
  const o = orden || await api("GET", `/api/compras/${numero}`).catch((e) => { toast(e.message, { error: true }); return null; });
  if (!o) return;
  let modo = store.estado.pin.bloqueado ? "otp" : "pin";
  const m = abrirModal("");
  const pintar = (error = "") => {
    m.el.innerHTML = `<div class="fila" style="gap:10px"><span class="marca-logo">${icono("candado", 18)}</span><h2>${modo === "pin" ? "Autoriza con tu PIN" : "Código por WhatsApp"}</h2></div>
      <p class="sub peq" style="margin-top:12px">${esc(o.numero)} · ${esc(o.proveedor)}${o.monto != null ? ` · ${soles(o.monto)}` : ""} se enviará al proveedor. ${o.origen === "AGENTE" ? "La propuso el agente; la autorizas tú." : ""}</p>
      ${modo === "pin" ? `<div class="pin-entrada"><input id="pin" type="password" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="••••" aria-label="PIN" style="width:200px;letter-spacing:.5em"></div>`
        : `<p class="peq tenue" style="text-align:center;margin-top:16px">Te enviamos un código de 6 dígitos por WhatsApp. En la demo lo ves en el Panel de demo.</p><div class="pin-entrada"><input id="pin" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="000000" aria-label="Código" style="width:220px;letter-spacing:.4em"></div>`}
      <p class="pin-error" role="alert">${esc(error)}</p>
      ${modo === "otp" && store.estado.whatsapp[0] ? `<div class="wsp" style="border:1px dashed var(--acento)"><b>Solo en la demo · WhatsApp a ${esc(store.estado.whatsapp[0].para)}</b>${esc(store.estado.whatsapp[0].texto)}</div>` : ""}
      <div class="fila entre" style="margin-top:12px">${modo === "pin" ? `<button class="enlace peq" data-otp>No tengo mi PIN · usar código por WhatsApp</button>` : `<button class="enlace peq" data-reenviar>Enviar otro código</button>`}
        <div class="fila"><button class="boton" data-cerrar>Cancelar</button><button class="boton primario" data-ok>Autorizar y enviar</button></div></div>`;
    m.el.querySelector("[data-cerrar]").addEventListener("click", m.cerrar);
    const inp = m.el.querySelector("#pin");
    inp.focus();
    inp.addEventListener("keydown", (ev) => ev.key === "Enter" && enviar());
    m.el.querySelector("[data-ok]").addEventListener("click", enviar);
    m.el.querySelector("[data-otp]")?.addEventListener("click", solicitarOtp);
    m.el.querySelector("[data-reenviar]")?.addEventListener("click", solicitarOtp);
  };
  async function solicitarOtp() {
    try { const r = await api("POST", "/api/compras/otp", {}); if (r.estado) (await import("./app.js")).setEstado(r.estado); modo = "otp"; pintar(); }
    catch (e) { pintar(e.message); }
  }
  async function enviar() {
    const valor = m.el.querySelector("#pin").value.trim();
    try {
      const r = await api("POST", `/api/compras/${o.numero}/enviar`, modo === "pin" ? { pin: valor } : { otp: valor });
      m.cerrar();
      toast(`${conPunto(`Enviaste ${o.numero} a ${o.proveedor}`)} Quedó registrado quién la autorizó.`);
      if (drawerAbierto()) pintarOrden(r);
      const app = await import("./app.js"); app.refrescar();
    } catch (e) {
      if (e.codigo === "PIN_BLOQUEADO") { modo = "otp"; await solicitarOtp(); pintar(e.message); return; }
      pintar(e.message);
      const app = await import("./app.js"); app.refrescar();
    }
  }
  if (modo === "otp") await solicitarOtp(); else pintar();
}
