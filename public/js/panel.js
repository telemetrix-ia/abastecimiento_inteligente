// Panel de demo: no es parte del ERP. Simula ventas y el paso del tiempo, dispara la corrida, cambia opciones del negocio.
import { accion, store } from "./app.js";
import { archivoABase64, descargarExcel } from "./api.js";
import { cerrarDrawer, confirmar, esc, fechaHora, fechaLarga, icono, soles, toast } from "./ui.js";

let abierto = null;
let ultimoResultado = "";

export function abrirPanel() {
  if (abierto) { cerrar(); return; }
  const el = document.createElement("aside");
  el.className = "panel-demo"; el.setAttribute("aria-label", "Panel de demo");
  document.body.appendChild(el);
  abierto = el;
  pintar();
  const tecla = (e) => e.key === "Escape" && !document.querySelector(".modal") && cerrar();
  document.addEventListener("keydown", tecla);
  el._tecla = tecla;
}

function cerrar() {
  if (!abierto) return;
  document.removeEventListener("keydown", abierto._tecla);
  abierto.remove(); abierto = null;
}

export function repintarPanel() { if (abierto) pintar(); }

function pintar() {
  const e = store.estado;
  if (!e || !abierto) return;
  const c = e.config;
  const enviadas = e.ocs.filter((o) => o.enviada_al_proveedor && ["APROBADA", "RECIBIDA_PARCIAL"].includes(o.estado));
  const interruptor = (campo, texto, valor) => `<label class="interruptor"><span>${texto}</span><input type="checkbox" data-config="${campo}" ${valor ? "checked" : ""}></label>`;
  abierto.innerHTML = `<div class="drawer-cab"><div style="flex:1"><h2>Panel de demo</h2><p class="sub peq">Controla la simulación. No es parte del ERP: el cliente nunca lo verá.</p></div>
      <button class="boton-icono" data-cerrar aria-label="Cerrar">${icono("cerrar")}</button></div>
    <div class="drawer-cuerpo">
      <section class="panel-sec"><h3>Tiempo y ventas</h3>
        <p class="peq" style="margin:0 0 10px"><b>${esc(fechaLarga(e.reloj))}</b> · la tienda vende de 10:00 a 20:00</p>
        <div class="fila" style="margin-bottom:8px"><label class="peq tenue" for="ritmo">Ritmo</label>
          <select class="campo" id="ritmo" style="height:34px;flex:1"><option value="1">Normal</option><option value="2" selected>Campaña (×2)</option><option value="3">Feriado largo (×3)</option></select></div>
        <div class="fila"><button class="boton chico" data-simular="24">Simular 1 día</button><button class="boton chico" data-simular="72">Simular 3 días</button><button class="boton chico" data-simular="4">4 horas</button></div>
        ${ultimoResultado ? `<p class="peq" style="margin:10px 0 0">${ultimoResultado}</p>` : ""}</section>
      <section class="panel-sec"><h3>Agente</h3>
        <p class="peq tenue" style="margin:0 0 10px">${e.cola.length} quiebre${e.cola.length === 1 ? "" : "s"} en cola. La corrida programada es a las ${esc(c.hora_corrida_programada)}.</p>
        <button class="boton primario" style="width:100%" data-corrida>${icono("reloj", 16)}Son las ${esc(c.hora_corrida_programada)} · correr el agente</button>
        ${enviadas.length ? `<button class="boton chico" style="width:100%;margin-top:12px" data-llegada-todas>${icono("camion", 16)}Llega todo lo enviado (${enviadas.length})</button><div class="fila" style="margin-top:8px"><select class="campo" id="llegada" style="height:34px;flex:1">${enviadas.map((o) => `<option value="${esc(o.numero)}">${esc(o.numero)} · ${esc(o.proveedor)}</option>`).join("")}</select>
          <button class="boton chico" data-llegada>${icono("camion", 16)}Simular llegada</button></div>` : ""}</section>
      <section class="panel-sec"><h3>Opciones del negocio</h3>
        ${interruptor("addon_multi_agente_activo", "Add-on IA Multi-Agente contratado", c.addon_multi_agente_activo)}
        ${interruptor("agente_abastecimiento_activo", "Agente de Abastecimiento activo", c.agente_abastecimiento_activo)}
        ${interruptor("restriccion_visualizacion_cruzada", "Cada usuario ve solo sus sucursales", c.restriccion_visualizacion_cruzada)}
        <div class="interruptor"><span>Tope de aprobación por monto</span><span class="fila"><span class="peq tenue">S/</span><input class="campo" style="width:96px;height:34px" type="number" min="0" step="50" value="${c.tope_aprobacion}" data-valor="tope_aprobacion"></span></div>
        <div class="interruptor"><span>Días de cobertura</span><input class="campo" style="width:96px;height:34px" type="number" min="1" max="90" value="${c.dias_cobertura}" data-valor="dias_cobertura"></div>
        <div class="interruptor"><span>Alcance del agente</span><select class="campo" style="height:34px" data-valor="alcance_modo">
          ${[["TODAS_CONSOLIDADO", "Todas, consolidado"], ["TODAS_POR_SEPARADO", "Por sucursal"]].map(([v, t]) => `<option value="${v}" ${c.alcance_modo === v ? "selected" : ""}>${t}</option>`).join("")}</select></div>
        <div class="interruptor"><span>Saldo de créditos</span><input class="campo" style="width:96px;height:34px" type="number" min="0" value="${e.creditos.saldo}" data-saldo></div>
        ${e.meta.ia_configurada ? `<div class="interruptor"><span>Motor de IA</span><select class="campo" style="height:34px" data-valor="modo_ia">
          <option value="auto" ${c.modo_ia !== "simulado" ? "selected" : ""}>OpenRouter · Nemotron</option><option value="simulado" ${c.modo_ia === "simulado" ? "selected" : ""}>IA simulada (respaldo)</option></select></div>`
          : `<p class="peq tenue">Motor de IA: simulado. Define OPENROUTER_API_KEY en el servidor para usar Nemotron.</p>`}</section>
      <section class="panel-sec"><h3>PIN y WhatsApp (simulado)</h3>
        ${e.meta.pin_demo ? `<p class="peq" style="margin:0">PIN de la Administradora para esta demo: <b>${esc(e.meta.pin_demo)}</b>. Tres intentos fallidos lo bloquean y se usa el código por WhatsApp.</p>` : ""}
        ${e.whatsapp.length ? e.whatsapp.map((w) => `<div class="wsp"><b>WhatsApp → ${esc(w.para)} · ${esc(fechaHora(w.ts))}</b>${esc(w.texto)}</div>`).join("") : `<p class="peq tenue">Aquí aparecen los mensajes de WhatsApp que el sistema enviaría.</p>`}</section>
      <section class="panel-sec"><h3>Datos</h3>
        <p class="peq tenue" style="margin:0 0 10px">Origen: ${esc(e.meta.origen_datos)}. Mismo formato que el Excel del notebook. Estado guardado en ${e.meta.almacen === "upstash" ? "Upstash Redis" : "archivo local"}.</p>
        <div class="fila"><button class="boton chico" data-descargar>Descargar Excel actual</button>
          <label class="boton chico">Cargar Excel<input type="file" accept=".xlsx" data-cargar class="sr"></label>
          <button class="boton chico peligro" data-reiniciar>Reiniciar demo</button></div></section>
    </div>`;
  enlazar();
}

function enlazar() {
  const el = abierto;
  el.querySelector("[data-cerrar]").addEventListener("click", cerrar);
  el.querySelectorAll("[data-simular]").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      const r = await accion("POST", "/api/demo/simular", { horas: Number(b.dataset.simular), intensidad: Number(el.querySelector("#ritmo").value) });
      const x = r.resultado;
      ultimoResultado = `Se vendieron <b>${x.unidades}</b> unidades (${soles(x.monto)}). ${x.nuevos_quiebres.length ? `<b>${x.nuevos_quiebres.length}</b> producto${x.nuevos_quiebres.length > 1 ? "s" : ""} cruzaron su mínimo: ${x.nuevos_quiebres.map((q) => esc(q.producto)).join(", ")}.` : "Ningún producto cruzó su mínimo."}`;
      toast(x.nuevos_quiebres.length ? `${x.nuevos_quiebres.length} producto(s) nuevos en la cola del agente` : "Ventas simuladas: sin quiebres nuevos");
    } catch { /* toast ya mostrado */ }
    pintar();
  }));
  el.querySelector("[data-corrida]").addEventListener("click", async (ev) => {
    ev.currentTarget.disabled = true; ev.currentTarget.textContent = "El agente está trabajando…";
    try {
      const r = await accion("POST", "/api/ia/corrida", {});
      const s = r.salida;
      const textos = { COMPLETADA: `Corrida terminada: ${s.borradores_oc.length} borrador(es) en Compras`, OMITIDA_SIN_EVENTOS: "Corrida omitida: no había quiebres nuevos (sin costo)",
        OMITIDA_SALDO_INSUFICIENTE: "La corrida no se inició: créditos insuficientes", SIN_PENDIENTES: "Corrida terminada: nada que reponer" };
      toast(textos[s.estado] || `Corrida: ${s.estado}`, s.estado === "COMPLETADA" ? { accion: "Revisar", onAccion: () => { cerrar(); location.hash = "#/compras?origen=IA"; } } : {});
    } catch { /* toast ya mostrado */ }
    pintar();
  });
  el.querySelector("[data-llegada-todas]")?.addEventListener("click", async () => {
    const r = await accion("POST", "/api/demo/llegada-todas", {}).catch(() => null);
    if (r) toast(`Llegó la mercadería de ${r.resultado.ordenes.length} orden(es): el stock está repuesto.`, { accion: "Ver ciclo", onAccion: () => { cerrar(); location.hash = "#/ciclo"; } });
    pintar();
  });
  el.querySelector("[data-llegada]")?.addEventListener("click", async () => {
    const numero = el.querySelector("#llegada").value;
    await accion("POST", "/api/demo/llegada", { numero }).then(() => toast(`Llegó la mercadería de ${numero}: el stock subió.`)).catch(() => {});
    pintar();
  });
  el.querySelectorAll("[data-config]").forEach((c) => c.addEventListener("change", () => accion("POST", "/api/demo/config", { campo: c.dataset.config, valor: c.checked }).then(pintar).catch(pintar)));
  el.querySelectorAll("[data-valor]").forEach((c) => c.addEventListener("change", () => accion("POST", "/api/demo/config", { campo: c.dataset.valor, valor: c.value }).then(pintar).catch(pintar)));
  el.querySelector("[data-saldo]").addEventListener("change", (ev) => accion("POST", "/api/demo/config", { campo: "saldo_creditos", valor: Number(ev.target.value) }).then(pintar).catch(pintar));
  el.querySelector("[data-descargar]").addEventListener("click", () => descargarExcel().catch((e) => toast(e.message, { error: true })));
  el.querySelector("[data-cargar]").addEventListener("change", async (ev) => {
    const archivo = ev.target.files[0];
    if (!archivo) return;
    if (archivo.size > 3.5 * 1024 * 1024) { toast("El archivo supera 3,5 MB", { error: true }); return; }
    if (!(await confirmar("Cargar este Excel", "La demo se reinicia con los datos del archivo. Se pierden las órdenes y conversaciones actuales.", "Cargar y reiniciar"))) return;
    try {
      const r = await accion("POST", "/api/demo/excel", { archivo_b64: await archivoABase64(archivo) });
      toast(`Datos cargados: ${r.productos} productos y ${r.ventas} días-producto de ventas.`);
      cerrarDrawer(); ultimoResultado = "";
    } catch { /* toast ya mostrado */ }
    pintar();
  });
  el.querySelector("[data-reiniciar]").addEventListener("click", async () => {
    if (!(await confirmar("Reiniciar la demo", "Vuelve al escenario inicial: 22 de octubre, 19:00, con 9 quiebres en cola. Se borran órdenes, conversaciones y auditoría de esta sesión.", "Reiniciar"))) return;
    await accion("POST", "/api/demo/reiniciar", {}).catch(() => {});
    ultimoResultado = ""; cerrarDrawer(); toast("Demo reiniciada."); pintar();
  });
}
