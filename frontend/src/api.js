// All calls to the FastAPI backend. In development Vite proxies /api to port 8000.
const BASE = import.meta.env.VITE_API_URL || "";

async function request(path, { json, ...options } = {}) {
  if (json !== undefined) {
    options.method = options.method || "POST";
    options.headers = { "Content-Type": "application/json", ...options.headers };
    options.body = JSON.stringify(json);
  }
  let res;
  try {
    res = await fetch(BASE + path, options);
  } catch {
    throw new Error("Can't reach the server. Check that the API is running on port 8000.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join(". ") : data.detail;
    if (detail) throw new Error(detail);
    throw new Error(
      res.status >= 500
        ? "The server isn't responding. Check that the API is running (uvicorn app:app --port 8000)."
        : `The request failed (${res.status}).`,
    );
  }
  return data;
}

export const api = {
  meta: () => request("/api/meta"),
  foundItems: () => request("/api/reports?kind=found"),
  lostItems: () => request("/api/reports?kind=lost"),
  report: (id) => request(`/api/reports/${id}`),
  matches: (id) => request(`/api/reports/${id}/matches`),
  createReport: (formData) => request("/api/reports", { method: "POST", body: formData }),
  autotag: (file) => {
    const body = new FormData();
    body.append("photo", file);
    return request("/api/autotag", { method: "POST", body });
  },
  answer: (id, attribute, answer) => request(`/api/reports/${id}/answer`, { json: { attribute, answer } }),
  startClaim: (foundId, lostId) => request("/api/claims", { json: { found_id: foundId, lost_id: lostId || null } }),
  claim: (id) => request(`/api/claims/${id}`),
  verifyClaim: (id, answer) => request(`/api/claims/${id}/verify`, { json: { answer } }),
  stats: () => request("/api/admin/stats"),
  confirmPickup: (code) => request(`/api/pickups/${encodeURIComponent(code)}`, { method: "POST" }),
};

export const photoUrl = (path) => (path ? BASE + path : null);
