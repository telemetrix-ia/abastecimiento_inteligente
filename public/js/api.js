// Cliente de la API. Cada navegador tiene su propia demo (X-Demo-Id); la clave de Anthropic nunca llega aquí.
import { abrirModal, esc } from "./ui.js";

const leer = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
const escribir = (k, v) => { try { localStorage.setItem(k, v); } catch { /* sin almacenamiento: vale para esta pestaña */ } };

let demoId = leer("demo_id");
if (!demoId || !/^[a-zA-Z0-9-]{8,64}$/.test(demoId)) {
  demoId = (crypto.randomUUID ? crypto.randomUUID() : "demo-" + Math.random().toString(36).slice(2) + Date.now().toString(36));
  escribir("demo_id", demoId);
}
let codigo = leer("demo_codigo") || "";

export class ErrorApi extends Error {
  constructor(mensaje, codigo, status) { super(mensaje); this.codigo = codigo; this.status = status; }
}

function pedirCodigo() {
  return new Promise((res) => {
    const m = abrirModal(`<h2>Código de acceso</h2><p class="sub">Esta demo está protegida. Escribe el código que te compartieron.</p>
      <input class="campo" id="cod" type="password" autocomplete="off" style="width:100%;margin-top:16px">
      <div class="fila" style="justify-content:flex-end;margin-top:20px"><button class="boton primario" id="ok">Entrar</button></div>`);
    const ok = () => { codigo = m.el.querySelector("#cod").value.trim(); escribir("demo_codigo", codigo); m.cerrar(); res(); };
    m.el.querySelector("#ok").addEventListener("click", ok);
    m.el.querySelector("#cod").addEventListener("keydown", (e) => e.key === "Enter" && ok());
    m.el.querySelector("#cod").focus();
  });
}

export async function api(metodo, ruta, cuerpo) {
  const r = await fetch(ruta, {
    method: metodo,
    headers: { "Content-Type": "application/json", "X-Demo-Id": demoId, ...(codigo ? { "X-Demo-Codigo": codigo } : {}) },
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  });
  let datos = {};
  try { datos = await r.json(); } catch { /* respuesta no JSON */ }
  if (r.status === 401 && datos.codigo === "CODIGO_ACCESO") { await pedirCodigo(); return api(metodo, ruta, cuerpo); }
  if (!r.ok) throw new ErrorApi(datos.error || `Error ${r.status}`, datos.codigo, r.status);
  return datos;
}

export async function descargarExcel() {
  const r = await fetch("/api/demo/excel", { headers: { "X-Demo-Id": demoId, ...(codigo ? { "X-Demo-Codigo": codigo } : {}) } });
  if (!r.ok) throw new ErrorApi("No se pudo generar el Excel", "EXCEL", r.status);
  const url = URL.createObjectURL(await r.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: "datos_abastecimiento_demo.xlsx" });
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export const archivoABase64 = (archivo) => new Promise((res, rej) => {
  const lector = new FileReader();
  lector.onload = () => res(String(lector.result).split(",")[1]);
  lector.onerror = () => rej(new Error("No se pudo leer el archivo"));
  lector.readAsDataURL(archivo);
});

export { esc };
