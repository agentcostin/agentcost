/* ── AgentCost: Model Pricing Registry ──────────────────────────────────────
 * Single source of truth for model names, providers, pricing, and metadata.
 * Updated: Feb 26, 2026 — reflects latest API pricing from official docs.
 *
 * Structure: { id, provider, label, input, output, tier, context, released }
 *   - input/output: USD per 1M tokens
 *   - tier: 'flagship' | 'balanced' | 'fast' | 'budget' | 'reasoning' | 'free'
 *   - context: max context window in K tokens
 */

window.AgentCost = window.AgentCost || {};

(function(ns) {

  ns.MODEL_REGISTRY = [
    // ── Anthropic Claude ─────────────────────────────────────────────────
    { id:'claude-opus-4-6',     provider:'Anthropic', label:'Claude Opus 4.6',        input:5.00,  output:25.00, tier:'flagship',  context:1000, released:'2026-02-05' },
    { id:'claude-sonnet-4-6',   provider:'Anthropic', label:'Claude Sonnet 4.6',      input:3.00,  output:15.00, tier:'balanced',  context:1000, released:'2026-02-17' },
    { id:'claude-opus-4-5',     provider:'Anthropic', label:'Claude Opus 4.5',        input:5.00,  output:25.00, tier:'flagship',  context:200,  released:'2025-11-01' },
    { id:'claude-sonnet-4-5',   provider:'Anthropic', label:'Claude Sonnet 4.5',      input:3.00,  output:15.00, tier:'balanced',  context:1000, released:'2025-09-29' },
    { id:'claude-haiku-4-5',    provider:'Anthropic', label:'Claude Haiku 4.5',       input:1.00,  output:5.00,  tier:'fast',      context:200,  released:'2025-10-01' },
    { id:'claude-sonnet-4',     provider:'Anthropic', label:'Claude Sonnet 4',        input:3.00,  output:15.00, tier:'balanced',  context:200,  released:'2025-05-22' },

    // ── OpenAI ───────────────────────────────────────────────────────────
    { id:'gpt-5.2',             provider:'OpenAI',    label:'GPT-5.2',                input:1.75,  output:14.00, tier:'flagship',  context:400,  released:'2025-12-15' },
    { id:'gpt-5.2-pro',         provider:'OpenAI',    label:'GPT-5.2 Pro',            input:21.00, output:168.00,tier:'flagship',  context:400,  released:'2025-12-15' },
    { id:'gpt-5.1',             provider:'OpenAI',    label:'GPT-5.1',                input:1.25,  output:10.00, tier:'flagship',  context:400,  released:'2025-11-01' },
    { id:'gpt-5.1-codex',       provider:'OpenAI',    label:'GPT-5.1 Codex',          input:1.25,  output:10.00, tier:'balanced',  context:400,  released:'2025-11-01' },
    { id:'gpt-5',               provider:'OpenAI',    label:'GPT-5',                  input:1.25,  output:10.00, tier:'flagship',  context:400,  released:'2025-08-07' },
    { id:'gpt-5-mini',          provider:'OpenAI',    label:'GPT-5 Mini',             input:0.25,  output:2.00,  tier:'fast',      context:400,  released:'2025-08-07' },
    { id:'gpt-5-nano',          provider:'OpenAI',    label:'GPT-5 Nano',             input:0.05,  output:0.40,  tier:'budget',    context:400,  released:'2025-08-07' },
    { id:'gpt-4.1',             provider:'OpenAI',    label:'GPT-4.1',                input:2.00,  output:8.00,  tier:'balanced',  context:1048, released:'2025-04-14' },
    { id:'gpt-4.1-mini',        provider:'OpenAI',    label:'GPT-4.1 Mini',           input:0.40,  output:1.60,  tier:'fast',      context:1048, released:'2025-04-14' },
    { id:'gpt-4.1-nano',        provider:'OpenAI',    label:'GPT-4.1 Nano',           input:0.10,  output:0.40,  tier:'budget',    context:1048, released:'2025-04-14' },
    { id:'gpt-4o',              provider:'OpenAI',    label:'GPT-4o',                 input:2.50,  output:10.00, tier:'balanced',  context:128,  released:'2024-05-13' },
    { id:'gpt-4o-mini',         provider:'OpenAI',    label:'GPT-4o Mini',            input:0.15,  output:0.60,  tier:'fast',      context:128,  released:'2024-07-18' },
    { id:'o4-mini',             provider:'OpenAI',    label:'o4 Mini',                input:1.10,  output:4.40,  tier:'reasoning', context:200,  released:'2025-04-16' },
    { id:'o3',                  provider:'OpenAI',    label:'o3',                     input:2.00,  output:8.00,  tier:'reasoning', context:200,  released:'2025-04-16' },
    { id:'o3-mini',             provider:'OpenAI',    label:'o3 Mini',                input:1.10,  output:4.40,  tier:'reasoning', context:200,  released:'2025-01-31' },

    // ── Google Gemini ────────────────────────────────────────────────────
    { id:'gemini-3-pro',        provider:'Google',    label:'Gemini 3 Pro',           input:2.00,  output:12.00, tier:'flagship',  context:1000, released:'2025-11-18' },
    { id:'gemini-2.5-pro',      provider:'Google',    label:'Gemini 2.5 Pro',         input:1.25,  output:10.00, tier:'balanced',  context:1000, released:'2025-06-17' },
    { id:'gemini-2.5-flash',    provider:'Google',    label:'Gemini 2.5 Flash',       input:0.15,  output:0.60,  tier:'fast',      context:1000, released:'2025-06-17' },
    { id:'gemini-2.5-flash-lite',provider:'Google',   label:'Gemini 2.5 Flash Lite',  input:0.10,  output:0.40,  tier:'budget',    context:1000, released:'2025-06-17' },
    { id:'gemini-2.0-flash',    provider:'Google',    label:'Gemini 2.0 Flash',       input:0.10,  output:0.40,  tier:'budget',    context:1000, released:'2025-02-01' },

    // ── xAI Grok ─────────────────────────────────────────────────────────
    { id:'grok-4',              provider:'xAI',       label:'Grok 4',                 input:3.00,  output:15.00, tier:'flagship',  context:256,  released:'2025-07-10' },
    { id:'grok-4-fast',         provider:'xAI',       label:'Grok 4 Fast',            input:0.20,  output:0.50,  tier:'fast',      context:2000, released:'2025-09-19' },
    { id:'grok-4.1-fast',       provider:'xAI',       label:'Grok 4.1 Fast',          input:0.20,  output:0.50,  tier:'fast',      context:2000, released:'2025-12-11' },

    // ── DeepSeek ─────────────────────────────────────────────────────────
    { id:'deepseek-chat',       provider:'DeepSeek',  label:'DeepSeek V3.2 Chat',     input:0.28,  output:0.42,  tier:'budget',    context:128,  released:'2025-09-29' },
    { id:'deepseek-reasoner',   provider:'DeepSeek',  label:'DeepSeek V3.2 Reasoner', input:0.28,  output:0.42,  tier:'reasoning', context:128,  released:'2025-09-29' },
    { id:'deepseek-r1',         provider:'DeepSeek',  label:'DeepSeek R1',            input:0.55,  output:2.19,  tier:'reasoning', context:128,  released:'2025-01-20' },

    // ── Local / Self-hosted ──────────────────────────────────────────────
    { id:'llama3:8b',           provider:'Local',     label:'Llama 3 8B',             input:0.0,   output:0.0,   tier:'free',      context:128,  released:'2024-04-18' },
    { id:'llama3:70b',          provider:'Local',     label:'Llama 3 70B',            input:0.0,   output:0.0,   tier:'free',      context:128,  released:'2024-04-18' },
    { id:'mistral',             provider:'Local',     label:'Mistral 7B',             input:0.0,   output:0.0,   tier:'free',      context:32,   released:'2023-09-27' },
    { id:'mixtral',             provider:'Local',     label:'Mixtral 8x7B',           input:0.0,   output:0.0,   tier:'free',      context:32,   released:'2023-12-11' },
    { id:'qwen2',               provider:'Local',     label:'Qwen 2',                 input:0.0,   output:0.0,   tier:'free',      context:128,  released:'2024-06-07' },
  ];

  // Helper: get model by id
  ns.getModel = function(id) {
    return ns.MODEL_REGISTRY.find(m => m.id === id);
  };

  // Helper: group by provider
  ns.getProviders = function() {
    const groups = {};
    ns.MODEL_REGISTRY.forEach(m => {
      if (!groups[m.provider]) groups[m.provider] = [];
      groups[m.provider].push(m);
    });
    return groups;
  };

  // Helper: models for dropdown (non-free only, plus one free)
  ns.getEstimatorModels = function() {
    return ns.MODEL_REGISTRY.filter(m => m.tier !== 'free' || m.id === 'llama3:8b');
  };

  // Helper: tier colors
  ns.TIER_COLORS = {
    flagship:  '#e85d3a',
    balanced:  '#60a5fa',
    fast:      '#34d399',
    budget:    '#fbbf24',
    reasoning: '#a78bfa',
    free:      '#6b7280',
  };

  // Helper: provider colors
  ns.PROVIDER_COLORS = {
    Anthropic: '#d4a574',
    OpenAI:    '#10a37f',
    Google:    '#4285f4',
    xAI:       '#1da1f2',
    DeepSeek:  '#00d4aa',
    Local:     '#6b7280',
  };

})(window.AgentCost);