/* ── AgentCost: Shared API & Utilities ──────────────────────────────────────
 * Shared across all dashboard modules. Loaded first.
 * Exposes: AgentCost.api, AgentCost.fmt$, AgentCost.fmtN, etc.
 */

window.AgentCost = window.AgentCost || {};

(function(ns) {
  const BASE = window.location.origin;
  let _token = null;
  try { _token = sessionStorage.getItem('agentcost_token'); } catch {}

  ns.setToken = function(t) {
    _token = t;
    try { if(t) sessionStorage.setItem('agentcost_token',t); else sessionStorage.removeItem('agentcost_token'); } catch {}
  };

  ns.api = async function(path, opts={}) {
    const headers = {'Content-Type':'application/json',...(opts.headers||{})};
    if (_token) headers['Authorization'] = `Bearer ${_token}`;
    try {
      const r = await fetch(BASE+path, {...opts, headers, credentials:'include'});
      if (r.ok) return r.json();
      if (r.status===401) ns.setToken(null);
      return null;
    } catch { return null; }
  };

  ns.apiPost = (p,b) => ns.api(p, {method:'POST', body:JSON.stringify(b)});
  ns.apiPut  = (p,b) => ns.api(p, {method:'PUT',  body:JSON.stringify(b)});
  ns.apiDel  = (p)    => ns.api(p, {method:'DELETE'});

  // Formatters
  ns.fmt$    = v => `$${(v||0).toFixed(4)}`;
  ns.fmtPct  = v => `${(v||0).toFixed(1)}%`;
  ns.fmtN    = v => (v||0).toLocaleString();
  ns.fmtTime = ts => ts && typeof ts==='string' ? ts.slice(11,19) : '';
  ns.fmtDate = ts => ts && typeof ts==='string' ? ts.slice(0,10) : '';

})(window.AgentCost);