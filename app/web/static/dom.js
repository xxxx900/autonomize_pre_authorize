// DOM helpers shared by the worksheet and the audit table. Every value goes in as textContent,
// never parsed as HTML, so record or audit text cannot inject markup.
"use strict";

export function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) { node.textContent = String(text); }
  if (cls) { node.className = cls; }
  return node;
}

export function add(parent, ...children) {
  for (const child of children) { parent.appendChild(child); }
  return parent;
}

/** A two-column table of field and value. */
export function factTable(facts) {
  const table = el("table", null, "facts");
  for (const f of facts) { table.appendChild(add(el("tr"), el("td", f.field), el("td", f.value))); }
  return table;
}

/** The token typed on either page, kept for this browser tab only. */
export function savedToken() {
  try { return sessionStorage.getItem("pa_token") || ""; } catch (e) { return ""; }
}

export function saveToken(token) {
  try { sessionStorage.setItem("pa_token", token); } catch (e) { /* storage unavailable */ }
}

/** GET a JSON API path with a bearer token. Returns {ok, status, body, traceId}. */
export async function getJson(path, token) {
  const response = await fetch(path, { headers: { "Authorization": "Bearer " + token } });
  const body = response.headers.get("content-type")?.includes("json") ? await response.json() : null;
  return { ok: response.ok, status: response.status, body, traceId: response.headers.get("X-Request-ID") };
}
