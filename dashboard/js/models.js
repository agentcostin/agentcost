/* -- AgentCost: Model Pricing Registry (Dynamic) --
 * Fetches 2,610+ models from /api/models instead of hardcoded array.
 * Falls back to curated static list if the API is unavailable.
 *
 * Exposes: AgentCost.MODEL_REGISTRY, .getModel(), .getProviders(),
 *          .getEstimatorModels(), .loadModels(), .searchModels(),
 *          .TIER_COLORS, .PROVIDER_COLORS
 */

window.AgentCost = window.AgentCost || {};

(function(ns) {

  // -- Static fallback (curated top models, used when API is down) --
  var FALLBACK_REGISTRY = [
    { id:'claude-sonnet-4-5',   provider:'anthropic', label:'Claude Sonnet 4.5',    input:3.00,  output:15.00, tier:'standard', context:1000 },
    { id:'claude-haiku-4-5',    provider:'anthropic', label:'Claude Haiku 4.5',     input:1.00,  output:5.00,  tier:'standard', context:200  },
    { id:'gpt-4o',              provider:'openai',    label:'GPT-4o',               input:2.50,  output:10.00, tier:'standard', context:128  },
    { id:'gpt-4o-mini',         provider:'openai',    label:'GPT-4o Mini',          input:0.15,  output:0.60,  tier:'economy',  context:128  },
    { id:'o1',                  provider:'openai',    label:'o1',                   input:15.00, output:60.00, tier:'premium',  context:200  },
    { id:'claude-3-opus-20240229',provider:'anthropic',label:'Claude 3 Opus',       input:15.00, output:75.00, tier:'premium',  context:200  },
    { id:'gpt-3.5-turbo',       provider:'openai',    label:'GPT-3.5 Turbo',       input:0.50,  output:1.50,  tier:'standard', context:16   },
    { id:'claude-3-haiku-20240307',provider:'anthropic',label:'Claude 3 Haiku',     input:0.25,  output:1.25,  tier:'economy',  context:200  },
  ];

  ns.MODEL_REGISTRY = FALLBACK_REGISTRY;
  ns._modelsLoaded = false;
  ns._modelsByProvider = {};
  ns._tierData = null;
  ns._providerList = [];

  // -- Load from API --

  ns.loadModels = async function(opts) {
    opts = opts || {};
    var limit = opts.limit || 5000;
    try {
      var r = await ns.api('/api/models?limit=' + limit + '&sort=provider');
      if (r && r.models && r.models.length > 0) {
        ns.MODEL_REGISTRY = r.models;
        ns._modelsLoaded = true;
        ns._rebuildIndexes();
        return r;
      }
    } catch(e) { console.warn('AgentCost: /api/models failed, using fallback', e); }
    ns._rebuildIndexes();
    return null;
  };

  ns.loadTiers = async function() {
    try {
      var r = await ns.api('/api/models/tiers');
      if (r) { ns._tierData = r; return r; }
    } catch(e) {}
    return null;
  };

  ns.loadProviders = async function() {
    try {
      var r = await ns.api('/api/models/providers');
      if (r && r.providers) { ns._providerList = r.providers; return r; }
    } catch(e) {}
    return null;
  };

  ns.searchModels = async function(query, filters) {
    filters = filters || {};
    var url = '/api/models/search?q=' + encodeURIComponent(query || '');
    if (filters.provider) url += '&provider=' + encodeURIComponent(filters.provider);
    if (filters.tier) url += '&tier=' + encodeURIComponent(filters.tier);
    if (filters.min_input != null) url += '&min_input=' + filters.min_input;
    if (filters.max_input != null) url += '&max_input=' + filters.max_input;
    if (filters.min_context != null) url += '&min_context=' + filters.min_context;
    if (filters.limit) url += '&limit=' + filters.limit;
    try { return await ns.api(url); } catch(e) { return null; }
  };

  // -- Helpers (backward-compatible) --

  ns._rebuildIndexes = function() {
    ns._modelsByProvider = {};
    ns.MODEL_REGISTRY.forEach(function(m) {
      var p = m.provider || 'unknown';
      if (!ns._modelsByProvider[p]) ns._modelsByProvider[p] = [];
      ns._modelsByProvider[p].push(m);
    });
  };

  ns.getModel = function(id) {
    return ns.MODEL_REGISTRY.find(function(m) { return m.id === id; });
  };

  ns.getProviders = function() { return ns._modelsByProvider; };

  ns.getEstimatorModels = function() {
    return ns.MODEL_REGISTRY.filter(function(m) { return m.tier !== 'free' || m.id === 'llama3:8b'; });
  };

  // -- Auto-load on page startup --
  if (typeof ns.api === 'function') {
    ns.loadModels(); ns.loadProviders();
  } else {
    var _tries = 0;
    var _poll = setInterval(function() {
      _tries++;
      if (typeof ns.api === 'function') { clearInterval(_poll); ns.loadModels(); ns.loadProviders(); }
      else if (_tries > 30) { clearInterval(_poll); ns._rebuildIndexes(); }
    }, 100);
  }

  // -- Color maps --
  ns.TIER_COLORS = {
    economy:'#34d399', standard:'#60a5fa', premium:'#e85d3a', free:'#6b7280',
    flagship:'#e85d3a', balanced:'#60a5fa', fast:'#34d399', budget:'#fbbf24', reasoning:'#a78bfa',
  };

  ns.PROVIDER_COLORS = {
    anthropic:'#d4a574', openai:'#10a37f', google:'#4285f4', vertex_ai:'#4285f4',
    groq:'#f55036', together_ai:'#6366f1', mistral:'#ff7000', deepseek:'#00d4aa',
    bedrock:'#ff9900', azure:'#0078d4', ai21:'#6d28d9', ollama:'#6b7280',
    replicate:'#3b82f6', fireworks_ai:'#ef4444',
    Anthropic:'#d4a574', OpenAI:'#10a37f', Google:'#4285f4', xAI:'#1da1f2', DeepSeek:'#00d4aa', Local:'#6b7280',
  };

  ns._rebuildIndexes();

})(window.AgentCost);
