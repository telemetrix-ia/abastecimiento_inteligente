// app-ai: chat del agente, 4 tarjetas de acceso rápido, bandeja de propuestas, créditos y estados bloqueados.
import { accion, store } from "./app.js";
import { abrirDrawer, esc, fechaHora, hora, icono, NOMBRE_TOOL, soles, textoAgente, toast } from "./ui.js";

const SUGERENCIAS = [
  "¿Qué productos están en quiebre ahora mismo?",
  "¿Cuánto debería pedir del collar de perlas blanco para Huallaga y por qué?",
  "¿A qué hora corre el agente y cuántos créditos me quedan?",
];

export function vistaIA(raiz) {
  let ocupado = false;
  let borrador = "";
  let pendiente = null;   // mensaje del usuario mientras la IA responde

  raiz.innerHTML = `<div class="caja-cab" style="margin-bottom:20px"><div><h1>Asistente IA</h1>
    <p class="sub">Pregunta por tu stock y tus compras. El Agente de Abastecimiento propone órdenes de compra; tú las revisas y las apruebas en Compras.</p></div></div>
    <div id="ia-cuerpo"><div class="ia-grid"><div class="caja chat"><div style="padding:24px;display:grid;gap:12px">
    <div class="esqueleto" style="height:22px;width:40%"></div><div class="esqueleto" style="height:80px"></div><div class="esqueleto" style="height:80px;width:70%"></div></div></div>
    <div class="lado"><div class="caja esqueleto" style="height:220px"></div><div class="caja esqueleto" style="height:180px"></div></div></div></div>`;
  const cuerpo = raiz.querySelector("#ia-cuerpo");

  function bloqueo(e) {
    const u = e.usuario;
    if (!u.puede["ia.chat"]) return { titulo: "No tienes acceso al asistente", texto: "Tu rol no incluye el chat de IA. Pídele acceso a tu Administrador." };
    if (!e.config.addon_multi_agente_activo) return { titulo: "La IA no está contratada", texto: "Contrata el add-on IA Asistencial o IA Multi-Agente para usar el chat. El Agente de Abastecimiento viene con IA Multi-Agente.", cta: "Ver add-ons en Suscripción" };
    if (e.creditos.saldo < e.creditos.costos.consulta_chat) return { titulo: "Se agotaron tus créditos de IA", texto: "Compra un paquete adicional o espera al próximo corte. Tus agentes siguen apagados hasta entonces.", cta: "Comprar créditos" };
    return null;
  }

  function medidor(e) {
    const pct = Math.max(0, Math.min(100, (e.creditos.saldo / Math.max(e.creditos.inicial, 1)) * 100));
    const clase = e.creditos.saldo <= e.creditos.reserva ? "rojo" : pct < 40 ? "ambar" : "";
    return `<span class="creditos-pill" title="Créditos de IA del negocio"><span>${e.creditos.saldo} créditos</span><span class="medidor ${clase}"><i style="width:${pct}%"></i></span></span>`;
  }

  function mensaje(m) {
    if (m.rol === "user") return `<div class="msg user">${esc(m.texto)}</div>`;
    const meta = [];
    if (m.tools?.length) meta.push(`<span>Consultó:</span><span class="tools">${[...new Set(m.tools)].map((t) => `<span class="tool">${esc(NOMBRE_TOOL[t] || t)}</span>`).join("")}</span>`);
    if (m.creditos) meta.push(`<span>−${m.creditos} crédito${m.creditos > 1 ? "s" : ""}</span>`);
    if (m.alertas?.includes("PIN_ENMASCARADO")) meta.push(`<span class="badge ambar">PIN oculto: no lo compartas por chat</span>`);
    if (m.estado === "RECHAZADA_SEGURIDAD") meta.push(`<span class="badge rojo">Bloqueado por seguridad</span>`);
    if (["BLOQUEADO", "OMITIDA_SALDO_INSUFICIENTE", "ERROR", "INCOMPLETA"].includes(m.estado)) meta.push(`<span class="badge ambar">${esc(m.codigo || m.estado)}</span>`);
    if (m.alertas?.includes("IA_RESPALDO")) meta.push(`<span class="badge ambar" title="El modelo de OpenRouter no respondió o no cerró el ciclo; respondió el respaldo">Respondió el respaldo</span>`);
    if (m.modelo) meta.push(`<span>${esc(m.modelo === "simulado" ? "IA simulada" : m.modelo.split("/").pop())} · ${esc(hora(m.ts))}</span>`);
    let cta = "";
    if (m.borradores?.length) cta = `<div class="cta"><a class="boton chico primario" href="#/compras?origen=IA">Revisar ${m.borradores.length} borrador${m.borradores.length > 1 ? "es" : ""} en Compras ›</a>
      <button class="boton chico" data-json>Ver salida JSON</button></div>`;
    return `<div class="msg assistant">${textoAgente(m.texto)}${cta}${meta.length ? `<div class="msg-meta">${meta.join("")}</div>` : ""}</div>`;
  }

  function historial(e) {
    // las corridas a demanda aparecen en el chat; se enriquecen con los borradores de la última salida
    return e.chat.map((m) => (m.rol === "assistant" && e.ultima_salida && m.request_id === e.ultima_salida.request_id && e.ultima_salida.modo !== "consulta")
      ? { ...m, borradores: e.ultima_salida.borradores_oc } : m);
  }

  function tarjetas(e) {
    const agente = e.config.agente_abastecimiento_activo;
    const puedeRecompra = agente && e.usuario.puede["compras.borrador_ia"];
    const motivoRecompra = !agente ? "Primero activa el Agente de Abastecimiento en Configuración › IA" : !e.usuario.puede["compras.borrador_ia"] ? "Tu rol no puede pedir sugerencias de recompra" : "";
    return `<div class="tarjetas-rapidas">
      <button class="tarjeta-rapida principal" data-recompra ${puedeRecompra && !ocupado ? "" : "disabled"} title="${esc(motivoRecompra || "Consolida ahora los quiebres acumulados en borradores de orden de compra")}">
        ${icono("carrito")}<b>Sugerir Recompra</b><span>${puedeRecompra ? `${e.cola.length} quiebre${e.cola.length === 1 ? "" : "s"} en cola` : esc(motivoRecompra)}</span></button>
      <button class="tarjeta-rapida" data-pregunta="¿Qué productos están en quiebre o por quebrar y cuánto stock les queda?" ${ocupado ? "disabled" : ""}>${icono("buscar")}<b>Localizar Stock</b><span>Qué está en quiebre y dónde</span></button>
      <button class="tarjeta-rapida" disabled title="Fuera de esta demo: requiere caja (core-account)">${icono("caja")}<b>Resumen de Caja</b><span>Fuera de esta demo</span></button>
      <button class="tarjeta-rapida" disabled title="Fuera de esta demo: requiere auditoría forense (app-audit)">${icono("escudo")}<b>Auditar Desvíos</b><span>Fuera de esta demo</span></button></div>`;
  }

  function lado(e) {
    const prop = e.bandeja;
    const proxima = e.config.hora_corrida_programada;
    return `<div class="lado">
      ${prop.length ? `<section class="caja compacta" aria-label="Propuestas del agente"><div class="caja-cab" style="margin-bottom:6px"><h2>${prop.length} propuesta${prop.length > 1 ? "s" : ""} por revisar</h2></div>
        ${prop.map((o) => `<a class="propuesta" href="#/compras/${esc(o.numero)}"><span class="badge ia">IA</span><span style="min-width:0"><b>${esc(o.numero)} · ${esc(o.proveedor || "Sin proveedor asignado")}</b>
          <small>${o.n_lineas} producto${o.n_lineas > 1 ? "s" : ""} · ${esc(o.estado_etiqueta)} · ${esc(fechaHora(o.creada_en))}</small></span><span class="monto">${o.monto != null ? soles(o.monto) : ""}</span></a>`).join("")}
      </section>` : ""}
      <section class="caja compacta"><div class="caja-cab" style="margin-bottom:8px"><h2>Agente de Abastecimiento</h2>
        <span class="badge ${e.config.agente_abastecimiento_activo ? "verde" : ""}"><span class="punto-estado"></span>${e.config.agente_abastecimiento_activo ? "Activo" : "Apagado"}</span></div>
        <div class="dato"><span>Próxima corrida</span><b>Hoy ${esc(proxima)}</b></div>
        <div class="dato"><span>Quiebres en cola</span><a href="#/stock" class="enlace">${e.cola.length} ›</a></div>
        <div class="dato"><span>Última corrida</span><b>${esc(fechaHora(e.config.ultima_corrida))}</b></div>
        <div class="dato"><span>Alcance</span><b>${e.config.alcance_modo === "TODAS_POR_SEPARADO" ? "Por sucursal" : e.config.alcance_modo === "ALGUNAS" ? "Algunas sucursales" : "Todas, consolidado"}</b></div>
        <div class="dato"><span>Cobertura deseada</span><b>${e.config.dias_cobertura} días</b></div>
      </section>
      <section class="caja compacta"><div class="caja-cab" style="margin-bottom:8px"><h2>Créditos de IA</h2>${medidor(e)}</div>
        <div class="dato"><span>Cada corrida del agente</span><b>${e.creditos.costos.corrida_abastecimiento} créditos</b></div>
        <div class="dato"><span>Cada consulta del chat</span><b>${e.creditos.costos.consulta_chat} crédito</b></div>
        <div class="dato"><span>Reserva para los agentes</span><b>${e.creditos.reserva} créditos</b></div>
        ${e.ultima_salida ? `<button class="boton chico" style="margin-top:12px;width:100%" data-json>${icono("json", 16)}Salida JSON de la última ejecución</button>` : ""}
      </section></div>`;
  }

  function pintar(e) {
    const b = bloqueo(e);
    if (b) {
      cuerpo.innerHTML = `<div class="caja bloqueo"><div class="icono-grande">${icono("candado", 26)}</div><h2>${esc(b.titulo)}</h2><p class="sub" style="margin:8px auto 20px">${esc(b.texto)}</p>
        ${b.cta ? `<button class="boton" disabled title="app-subscription está fuera de esta demo">${esc(b.cta)}</button>` : ""}</div>`;
      return;
    }
    const msgs = historial(e);
    const banner = !e.config.agente_abastecimiento_activo ? `<div class="aviso ambar" style="margin-bottom:16px">${icono("info")}<div>Tu Agente de Abastecimiento está disponible pero inactivo. Actívalo en Configuración › IA (en esta demo, desde el Panel de demo) para que convierta los quiebres en borradores de compra.</div></div>` : "";
    const modelo = e.meta.modo_ia === "openrouter" ? `OpenRouter · ${e.meta.modelo}` : e.meta.ia_configurada ? "IA simulada (elegida en el Panel de demo)" : "IA simulada (sin clave de OpenRouter)";
    cuerpo.innerHTML = `${banner}<div class="ia-grid"><section class="caja chat" aria-label="Chat">
      <div class="chat-cab"><h2>Conversación</h2><span class="modelo" title="El modelo lo define la plataforma">${icono("candado", 14)}${esc(modelo)}</span>
        ${msgs.length ? `<button class="boton chico fantasma" data-limpiar>Nueva conversación</button>` : ""}${medidor(e)}</div>
      <div class="mensajes" id="mensajes" aria-live="polite">${msgs.length || pendiente ? msgs.map(mensaje).join("") : `<div class="vacio-chat"><h2>¿Qué necesitas reponer hoy?</h2>
        <p>Pregúntame por tu stock, tus ventas o por qué el agente sugirió una cantidad. Para que arme las órdenes, usa «Sugerir Recompra».</p>
        <div class="fila" style="justify-content:center;margin-top:16px">${SUGERENCIAS.map((s) => `<button class="chip" data-pregunta="${esc(s)}">${esc(s)}</button>`).join("")}</div></div>`}
        ${pendiente ? `${pendiente.texto ? `<div class="msg user">${esc(pendiente.texto)}</div>` : ""}<div class="msg assistant" aria-label="El asistente está trabajando"><div class="esqueleto" style="height:14px;width:260px;margin-bottom:8px"></div><div class="esqueleto" style="height:14px;width:180px"></div>
          <div class="msg-meta">${esc(pendiente.nota)}</div></div>` : ""}</div>
      ${tarjetas(e)}
      <form class="entrada" id="form-chat"><label class="sr" for="caja-texto">Tu consulta</label>
        <textarea id="caja-texto" rows="1" maxlength="600" placeholder="Escribe tu consulta…" ${ocupado ? "disabled" : ""}>${esc(borrador)}</textarea>
        <button class="boton primario" type="submit" ${ocupado ? "disabled" : ""} aria-label="Enviar">${icono("enviar", 18)}</button></form>
    </section>${lado(e)}</div>`;
    const lista = cuerpo.querySelector("#mensajes");
    lista.scrollTop = lista.scrollHeight;
    enlazar(e);
  }

  async function preguntar(texto) {
    if (ocupado || !texto.trim()) return;
    ocupado = true; borrador = ""; pendiente = { texto, nota: "Consultando tus datos…" };
    pintar(store.estado);
    try { await accion("POST", "/api/ia/chat", { mensaje: texto }); }
    catch { borrador = texto; }
    finally { ocupado = false; pendiente = null; pintar(store.estado); cuerpo.querySelector("#caja-texto")?.focus(); }
  }

  async function recompra() {
    if (ocupado) return;
    ocupado = true; pendiente = { texto: "Sugerir Recompra", nota: "El agente está consolidando los quiebres acumulados…" };
    pintar(store.estado);
    try {
      const r = await accion("POST", "/api/ia/recompra", {});
      const s = r.salida;
      if (s.estado === "COMPLETADA") toast(`El agente dejó ${s.borradores_oc.length} borrador(es) en Compras`, { accion: "Revisar", onAccion: () => (location.hash = "#/compras?origen=IA") });
    } catch { /* el toast de error ya se mostró */ }
    finally { ocupado = false; pendiente = null; pintar(store.estado); }
  }

  function verJSON() {
    const s = store.estado.ultima_salida;
    abrirDrawer({ ancho: true, cabecera: `<h2>Salida JSON del agente</h2><p class="sub peq">Contrato v${esc(s.version_contrato)} · ${esc(s.rf)} · modo ${esc(s.modo)} · estado ${esc(s.estado)}</p>`,
      cuerpo: `<p class="ayuda">Esto es lo que el agente devuelve a core-account y a la auditoría. Los borradores y las cantidades los arma el código a partir de los datos; el modelo solo redacta la respuesta.</p><pre class="json">${esc(JSON.stringify(s, null, 2))}</pre>` });
  }

  function enlazar(e) {
    const caja = cuerpo.querySelector("#caja-texto");
    caja?.addEventListener("input", () => { borrador = caja.value; caja.style.height = "auto"; caja.style.height = Math.min(caja.scrollHeight, 140) + "px"; });
    caja?.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); preguntar(caja.value); } });
    cuerpo.querySelector("#form-chat")?.addEventListener("submit", (ev) => { ev.preventDefault(); preguntar(caja.value); });
    cuerpo.querySelectorAll("[data-pregunta]").forEach((b) => b.addEventListener("click", () => preguntar(b.dataset.pregunta)));
    cuerpo.querySelector("[data-recompra]")?.addEventListener("click", recompra);
    cuerpo.querySelectorAll("[data-json]").forEach((b) => b.addEventListener("click", verJSON));
    cuerpo.querySelector("[data-limpiar]")?.addEventListener("click", () => accion("POST", "/api/ia/chat/limpiar", {}));
  }

  if (store.estado) pintar(store.estado);
  return { actualizar: (e) => { if (!ocupado) pintar(e); } };
}
