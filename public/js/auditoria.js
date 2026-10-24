// Auditoría: rastro forense encadenado por hash (core-audit) y log técnico separado (core-observabilidad).
import { api } from "./api.js";
import { abrirDrawer, esc, fechaHora, icono, toast } from "./ui.js";

const ACTOR = { AGENTE: "ia", USUARIO: "azul", SISTEMA: "" };
const SEV = { ALTA: "rojo", MEDIA: "ambar", BAJA: "" };

export function vistaAuditoria(raiz) {
  let pestana = "auditoria", filtro = "", datos = null;
  raiz.innerHTML = `<h1>Auditoría</h1><p class="sub">Todo lo que hizo el agente y lo que autorizó cada persona. Cada registro guarda el hash del anterior: si alguien altera uno, la cadena se rompe.</p>
    <div id="a-cuerpo" style="margin-top:24px"><div class="caja esqueleto" style="height:420px"></div></div>`;
  const cuerpo = raiz.querySelector("#a-cuerpo");

  async function cargar() {
    try { datos = await api("GET", "/api/auditoria"); pintar(); } catch (e) { toast(e.message, { error: true }); }
  }

  function pintar() {
    if (!datos) return;
    const regs = datos.registros.filter((r) => !filtro || r.actor_tipo === filtro);
    cuerpo.innerHTML = `<div class="fila entre" style="margin-bottom:14px"><div class="fila">
        <button class="chip" data-p="auditoria" aria-pressed="${pestana === "auditoria"}">Auditoría · ${datos.total}</button>
        <button class="chip" data-p="log" aria-pressed="${pestana === "log"}">Log técnico</button>
        ${pestana === "auditoria" ? [["", "Todos"], ["AGENTE", "Solo agente"], ["USUARIO", "Solo personas"]].map(([v, t]) => `<button class="chip" data-a="${v}" aria-pressed="${filtro === v}">${t}</button>`).join("") : ""}</div>
      <span class="badge ${datos.integra ? "verde" : "rojo"}">${icono("auditoria", 14)}${datos.integra ? "Cadena íntegra" : "Cadena alterada"}</span></div>
      ${pestana === "auditoria" ? `<div class="caja tabla-caja"><table class="tabla"><thead><tr><th>Registro<small>hora simulada</small></th><th>Actor</th><th>Acción</th><th>Recurso</th><th>Resultado</th></tr></thead>
        <tbody>${regs.map((r) => `<tr class="clic" data-id="${esc(r.audit_id)}"><td><b>${esc(r.audit_id)}</b><small>${esc(fechaHora(r.ts))}</small></td>
          <td><span class="badge ${ACTOR[r.actor_tipo] || ""}">${esc(r.actor_tipo === "AGENTE" ? "Agente" : r.actor_tipo === "USUARIO" ? "Persona" : "Sistema")}</span><small>${esc(r.actor_id)}</small></td>
          <td>${esc(r.accion.replaceAll("_", " ").toLowerCase())}${r.corrida_id ? `<small>${esc(r.corrida_id)}</small>` : ""}</td><td>${esc(r.recurso || "—")}</td>
          <td><span class="badge ${r.resultado === "OK" ? "" : SEV[r.severidad] || "ambar"}">${esc(r.resultado)}</span></td></tr>`).join("")}</tbody></table></div>`
      : `<p class="ayuda">El log técnico va aparte y nunca guarda el texto de las consultas, el PIN ni datos de negocio: solo latencias, estados y un hash de la entrada.</p>
        <div class="caja tabla-caja"><table class="tabla"><thead><tr><th>Hora</th><th>Evento</th><th>Detalle</th></tr></thead><tbody>${datos.log_tecnico.map((l) => `<tr><td>${esc(fechaHora(l.ts))}</td><td>${esc(l.evento)}<small>${esc(l.nivel)}</small></td>
          <td class="peq">${esc(Object.entries(l).filter(([k]) => !["ts", "evento", "nivel", "tenant_id"].includes(k) && l[k] != null).map(([k, v]) => `${k}: ${v}`).join(" · "))}</td></tr>`).join("")}</tbody></table></div>`}`;
    cuerpo.querySelectorAll("[data-p]").forEach((b) => b.addEventListener("click", () => { pestana = b.dataset.p; pintar(); }));
    cuerpo.querySelectorAll("[data-a]").forEach((b) => b.addEventListener("click", () => { filtro = b.dataset.a; pintar(); }));
    cuerpo.querySelectorAll("[data-id]").forEach((tr) => tr.addEventListener("click", () => {
      const r = datos.registros.find((x) => x.audit_id === tr.dataset.id);
      abrirDrawer({ cabecera: `<h2>${esc(r.audit_id)} · ${esc(r.accion)}</h2><p class="sub peq">${esc(fechaHora(r.ts))} · ${esc(r.actor_id)}${r.en_nombre_de && r.en_nombre_de !== r.actor_id ? ` en nombre de ${esc(r.en_nombre_de)}` : ""}</p>`,
        cuerpo: `<pre class="json">${esc(JSON.stringify(r.detalle, null, 2))}</pre><h3 class="seccion-titulo">Encadenamiento</h3>
          <div class="dato"><span>Hash anterior</span><span class="hash">${esc(r.prev_hash.slice(0, 24))}…</span></div><div class="dato"><span>Hash de este registro</span><span class="hash">${esc(r.hash.slice(0, 24))}…</span></div>` });
    }));
  }
  cargar();
  return { actualizar: cargar };
}
