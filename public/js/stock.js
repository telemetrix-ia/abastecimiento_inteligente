// Stock (vista mínima para la demo): stock por almacén, quiebres y la cola que espera el agente.
import { store } from "./app.js";
import { esc, fechaHora, icono } from "./ui.js";

export function vistaStock(raiz) {
  let filtro = "todos";
  raiz.innerHTML = `<h1>Stock</h1><p class="sub">Lo que tienes en cada almacén frente a su mínimo. Cuando un producto cruza su mínimo, el sistema avisa al Agente de Abastecimiento.</p>
    <div id="s-cuerpo" style="margin-top:24px"><div class="caja esqueleto" style="height:420px"></div></div>`;
  const cuerpo = raiz.querySelector("#s-cuerpo");

  function pintar(e) {
    if (!e.usuario.puede["stock.ver"]) { cuerpo.innerHTML = `<div class="caja bloqueo"><h2>No tienes acceso a Stock</h2></div>`; return; }
    const filas = e.stock.filter((s) => filtro === "todos" || s.estado === filtro)
      .sort((a, b) => (a.stock - a.minimo) / Math.max(a.minimo, 1) - (b.stock - b.minimo) / Math.max(b.minimo, 1));
    const n = (estado) => e.stock.filter((s) => s.estado === estado).length;
    cuerpo.innerHTML = `<div class="bento">
      <section class="caja" style="grid-column:span 8"><div class="caja-cab"><h2>Por almacén</h2><div class="fila">
        ${[["todos", `Todos · ${e.stock.length}`], ["quiebre", `En quiebre · ${n("quiebre")}`], ["bajo", `Cerca del mínimo · ${n("bajo")}`]].map(([id, t]) => `<button class="chip" data-f="${id}" aria-pressed="${filtro === id}">${t}</button>`).join("")}</div></div>
        <div style="overflow-x:auto;margin:0 -24px -24px"><table class="tabla"><thead><tr><th style="padding-left:24px">Producto</th><th>Almacén</th><th class="der">Stock</th><th>Frente al mínimo</th><th class="der">En camino</th><th class="der">Vendidas<small>hoy · 7 días</small></th></tr></thead>
        <tbody>${filas.map((s) => {
          const pct = Math.min(100, (s.stock / Math.max(s.minimo * 2, 1)) * 100);
          const color = s.estado === "quiebre" ? "var(--rojo)" : s.estado === "bajo" ? "var(--ambar)" : "var(--verde)";
          return `<tr><td style="padding-left:24px"><b>${esc(s.producto)}</b><small>${esc(s.variante)} · ${esc(s.sku)}</small></td><td>${esc(s.almacen)}</td>
            <td class="der"><b>${s.stock}</b><small>mín. ${s.minimo}</small></td>
            <td><span class="medidor-stock" title="Mínimo ${s.minimo}"><i style="width:${pct}%;background:${color}"></i><em style="left:50%"></em></span>
              ${s.estado === "quiebre" ? '<small style="color:var(--rojo)">En quiebre</small>' : s.estado === "bajo" ? '<small style="color:var(--ambar)">Cerca del mínimo</small>' : ""}</td>
            <td class="der">${s.en_transito || "—"}</td><td class="der">${s.vendidas_hoy} · ${s.vendidas_7d}</td></tr>`;
        }).join("")}</tbody></table></div></section>
      <section class="caja" style="grid-column:span 4"><div class="caja-cab"><h2>Cola del agente</h2><span class="badge ${e.cola.length ? "ia" : ""}">${e.cola.length}</span></div>
        <p class="ayuda">Quiebres que el agente todavía no convirtió en borradores. Los procesa a las ${esc(e.config.hora_corrida_programada)} o al pulsar «Sugerir Recompra».</p>
        ${e.cola.length ? e.cola.map((c) => `<div class="dato"><span><b style="color:var(--texto)">${esc(c.producto)}</b><br><small class="tenue">${esc(c.almacen)} · ${c.tipo === "CONSUMO_RESERVA" ? "consumió la reserva" : "cruzó su mínimo"}</small></span><small class="tenue">${esc(fechaHora(c.fecha_hora))}</small></div>`).join("")
          : `<p class="tenue">${icono("info", 16)} Sin quiebres pendientes. Simula ventas desde el Panel de demo.</p>`}
        ${e.cola.length ? `<a class="boton chico" style="margin-top:16px;width:100%" href="#/ia">${icono("ia", 16)}Ir a Sugerir Recompra</a>` : ""}
      </section></div>`;
    cuerpo.querySelectorAll("[data-f]").forEach((b) => b.addEventListener("click", () => { filtro = b.dataset.f; pintar(e); }));
  }
  if (store.estado) pintar(store.estado);
  return { actualizar: pintar };
}
