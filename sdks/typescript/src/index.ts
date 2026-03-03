/**
 * @agentcost/sdk — drop-in LLM cost tracking for TypeScript/JavaScript
 *
 * Usage:
 *   import OpenAI from 'openai';
 *   import { trace, getTracker } from '@agentcost/sdk';
 *
 *   const client = trace(new OpenAI(), { project: 'my-app' });
 *   const res = await client.chat.completions.create({ model: 'gpt-4o', messages: [...] });
 *   console.log(getTracker('my-app').summary());
 */

// ── Types ────────────────────────────────────────────────────────────────────

export interface TraceEvent {
  traceId: string;
  project: string;
  model: string;
  provider: string;
  inputTokens: number;
  outputTokens: number;
  cost: number;
  latencyMs: number;
  status: "success" | "error";
  error?: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
  agentId?: string;
}

export interface TraceOptions {
  project?: string;
  agentId?: string;
  persist?: boolean;
  onTrace?: (event: TraceEvent) => void;
}

export interface TrackerSummary {
  project: string;
  totalCost: number;
  totalCalls: number;
  totalInputTokens: number;
  totalOutputTokens: number;
  costByModel: Record<string, number>;
}

export interface AgentCostConfig {
  apiKey?: string;
  endpoint?: string;
  project?: string;
  batchSize?: number;
  flushIntervalMs?: number;
}

// ── Pricing (per 1M tokens) ──────────────────────────────────────────────────

const MODEL_PRICING: Record<string, { input: number; output: number }> = {
  "gpt-4o":             { input: 2.50,  output: 10.00 },
  "gpt-4o-mini":        { input: 0.15,  output: 0.60  },
  "gpt-4-turbo":        { input: 10.00, output: 30.00 },
  "gpt-3.5-turbo":      { input: 0.50,  output: 1.50  },
  "o1":                 { input: 15.00, output: 60.00 },
  "o1-mini":            { input: 3.00,  output: 12.00 },
  "o3-mini":            { input: 1.10,  output: 4.40  },
  "claude-sonnet-4-20250514": { input: 3.00, output: 15.00 },
  "claude-haiku-4-5-20251001":  { input: 0.80, output: 4.00 },
  "claude-opus-4-20250514":   { input: 15.00, output: 75.00 },
  "gemini-2.0-flash":   { input: 0.10,  output: 0.40  },
  "gemini-1.5-pro":     { input: 1.25,  output: 5.00  },
  "deepseek-chat":      { input: 0.14,  output: 0.28  },
};

function calculateCost(model: string, inputTokens: number, outputTokens: number): number {
  const pricing = MODEL_PRICING[model] ?? { input: 1.0, output: 2.0 };
  return (inputTokens * pricing.input + outputTokens * pricing.output) / 1_000_000;
}

// ── CostTracker ──────────────────────────────────────────────────────────────

class CostTracker {
  project: string;
  totalCost = 0;
  totalCalls = 0;
  totalInputTokens = 0;
  totalOutputTokens = 0;
  traces: TraceEvent[] = [];
  private callbacks: ((e: TraceEvent) => void)[] = [];

  constructor(project: string) {
    this.project = project;
  }

  record(event: TraceEvent) {
    this.traces.push(event);
    this.totalCost += event.cost;
    this.totalCalls++;
    this.totalInputTokens += event.inputTokens;
    this.totalOutputTokens += event.outputTokens;
    for (const cb of this.callbacks) {
      try { cb(event); } catch {}
    }
  }

  onTrace(callback: (e: TraceEvent) => void) {
    this.callbacks.push(callback);
  }

  summary(): TrackerSummary {
    const costByModel: Record<string, number> = {};
    for (const t of this.traces) {
      costByModel[t.model] = (costByModel[t.model] ?? 0) + t.cost;
    }
    return {
      project: this.project,
      totalCost: Math.round(this.totalCost * 1e6) / 1e6,
      totalCalls: this.totalCalls,
      totalInputTokens: this.totalInputTokens,
      totalOutputTokens: this.totalOutputTokens,
      costByModel,
    };
  }

  reset() {
    this.totalCost = 0;
    this.totalCalls = 0;
    this.totalInputTokens = 0;
    this.totalOutputTokens = 0;
    this.traces = [];
  }
}

// ── Tracker registry ─────────────────────────────────────────────────────────

const trackers = new Map<string, CostTracker>();

export function getTracker(project = "default"): CostTracker {
  let t = trackers.get(project);
  if (!t) {
    t = new CostTracker(project);
    trackers.set(project, t);
  }
  return t;
}

export function getAllTrackers(): Record<string, CostTracker> {
  return Object.fromEntries(trackers);
}

// ── Remote batch sender ──────────────────────────────────────────────────────

let _config: AgentCostConfig = {};
let _buffer: Record<string, unknown>[] = [];
let _flushTimer: ReturnType<typeof setInterval> | null = null;

export function init(config: AgentCostConfig) {
  _config = config;
  if (_config.flushIntervalMs && _config.flushIntervalMs > 0) {
    if (_flushTimer) clearInterval(_flushTimer);
    _flushTimer = setInterval(() => flush(), _config.flushIntervalMs);
  }
}

export async function flush(): Promise<void> {
  if (!_buffer.length || !_config.endpoint) return;
  const batch = _buffer.splice(0);
  const url = `${_config.endpoint.replace(/\/$/, "")}/api/trace/batch`;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_config.apiKey) headers["Authorization"] = `Bearer ${_config.apiKey}`;
  try {
    await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({ events: batch }),
    });
  } catch (e) {
    // Push back on failure
    _buffer.unshift(...batch);
  }
}

function _bufferEvent(event: TraceEvent) {
  if (!_config.endpoint) return;
  _buffer.push({
    model: event.model,
    provider: event.provider,
    project: event.project,
    agent_id: event.agentId,
    input_tokens: event.inputTokens,
    output_tokens: event.outputTokens,
    cost: event.cost,
    latency_ms: event.latencyMs,
    status: event.status,
    error: event.error,
  });
  if (_buffer.length >= (_config.batchSize ?? 50)) {
    flush();
  }
}

// ── Trace helper ─────────────────────────────────────────────────────────────

function uid(): string {
  return Math.random().toString(36).slice(2, 14);
}

function detectProvider(client: any): string {
  const mod = client?.constructor?.name ?? "";
  if (mod.includes("Anthropic")) return "anthropic";
  if (mod.includes("OpenAI")) return "openai";
  return "unknown";
}

// ── Proxy-based tracing (preserves typeof) ───────────────────────────────────

/**
 * Wrap an OpenAI or Anthropic client with cost tracking.
 * Returns a Proxy — typeof traced === typeof original.
 */
export function trace<T extends object>(client: T, opts: TraceOptions = {}): T {
  const project = opts.project ?? _config.project ?? "default";
  const provider = detectProvider(client);
  const tracker = getTracker(project);

  // Deep proxy: intercept .create() calls on chat.completions / messages
  function proxyTarget(target: any, path: string[]): any {
    return new Proxy(target, {
      get(obj, prop: string) {
        const value = obj[prop];

        // Intercept .create() on completions or messages
        if (prop === "create" && typeof value === "function") {
          const parentPath = path.join(".");
          if (
            parentPath.includes("completions") ||
            parentPath.includes("messages")
          ) {
            return async (...args: any[]) => {
              const kwargs = args[0] ?? {};
              const model: string = kwargs.model ?? "unknown";
              const start = performance.now();

              try {
                const result = await value.apply(obj, args);
                const latencyMs = performance.now() - start;

                let inputTokens = 0;
                let outputTokens = 0;

                // OpenAI format
                if (result?.usage?.prompt_tokens != null) {
                  inputTokens = result.usage.prompt_tokens;
                  outputTokens = result.usage.completion_tokens ?? 0;
                }
                // Anthropic format
                else if (result?.usage?.input_tokens != null) {
                  inputTokens = result.usage.input_tokens;
                  outputTokens = result.usage.output_tokens ?? 0;
                }

                const event: TraceEvent = {
                  traceId: uid(),
                  project,
                  model,
                  provider,
                  inputTokens,
                  outputTokens,
                  cost: calculateCost(model, inputTokens, outputTokens),
                  latencyMs,
                  status: "success",
                  timestamp: new Date().toISOString(),
                  agentId: opts.agentId,
                };

                tracker.record(event);
                opts.onTrace?.(event);
                if (opts.persist !== false) _bufferEvent(event);

                return result;
              } catch (err: any) {
                const latencyMs = performance.now() - start;
                const event: TraceEvent = {
                  traceId: uid(),
                  project,
                  model,
                  provider,
                  inputTokens: 0,
                  outputTokens: 0,
                  cost: 0,
                  latencyMs,
                  status: "error",
                  error: String(err).slice(0, 500),
                  timestamp: new Date().toISOString(),
                  agentId: opts.agentId,
                };
                tracker.record(event);
                opts.onTrace?.(event);
                if (opts.persist !== false) _bufferEvent(event);
                throw err;
              }
            };
          }
        }

        // Recurse into nested objects (chat → completions, messages)
        if (value && typeof value === "object" && !Array.isArray(value)) {
          return proxyTarget(value, [...path, prop]);
        }

        return value;
      },
    });
  }

  return proxyTarget(client, []) as T;
}
