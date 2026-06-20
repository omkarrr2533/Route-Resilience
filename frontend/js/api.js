// Thin wrapper over the compute service. API_BASE is empty when the dashboard is served by
// the FastAPI app itself (the one-process dev demo); point it at the Spring Boot gateway
// (http://localhost:8080) to exercise the full cached architecture.
const API_BASE = "";

const Api = {
  async _get(path, params) {
    const qs = params ? "?" + new URLSearchParams(params) : "";
    const res = await fetch(`${API_BASE}/api${path}${qs}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `${res.status} ${res.statusText}`);
    }
    return res.json();
  },

  health() { return this._get("/health"); },
  samples() { return this._get("/samples"); },
  criticality(source, weight) { return this._get("/criticality", { source, weight }); },
  impact(u, v, source, weight) { return this._get("/impact", { u, v, source, weight }); },
  robustness(source, weight, steps = 16) { return this._get("/robustness", { source, weight, steps }); },
};
