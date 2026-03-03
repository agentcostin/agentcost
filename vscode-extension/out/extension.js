"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
// ── AgentCost API Client ─────────────────────────────────────────────────────
class AgentCostClient {
    constructor() {
        const config = vscode.workspace.getConfiguration('agentcost');
        this.endpoint = config.get('endpoint', 'http://localhost:8100');
        this.apiKey = config.get('apiKey', '');
    }
    async fetch(path) {
        const url = `${this.endpoint}${path}`;
        const headers = { 'Content-Type': 'application/json' };
        if (this.apiKey)
            headers['X-API-Key'] = this.apiKey;
        try {
            const resp = await fetch(url, { headers });
            if (!resp.ok)
                throw new Error(`HTTP ${resp.status}`);
            return await resp.json();
        }
        catch (e) {
            vscode.window.showWarningMessage(`AgentCost: ${e.message}`);
            return null;
        }
    }
    async getSummary() { return this.fetch('/api/summary'); }
    async getTraces(limit = 20) { return this.fetch(`/api/traces?limit=${limit}`); }
    async getBudgets() { return this.fetch('/api/budgets'); }
    async getCostByModel() { return this.fetch('/api/cost/by-model'); }
}
// ── Cost Summary Tree ────────────────────────────────────────────────────────
class CostSummaryProvider {
    constructor(client) {
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
        this.items = [];
        this.client = client;
    }
    refresh() {
        this.loadData().then(() => this._onDidChangeTreeData.fire(undefined));
    }
    async loadData() {
        const summary = await this.client.getSummary();
        const byModel = await this.client.getCostByModel();
        this.items = [];
        if (summary) {
            this.items.push(new CostItem(`Total Cost: $${summary.total_cost?.toFixed(4) || '0'}`, 'stat'));
            this.items.push(new CostItem(`Total Calls: ${summary.total_calls || 0}`, 'stat'));
            this.items.push(new CostItem(`Total Tokens: ${(summary.total_tokens || 0).toLocaleString()}`, 'stat'));
        }
        if (byModel && Array.isArray(byModel)) {
            this.items.push(new CostItem('── By Model ──', 'header'));
            for (const m of byModel) {
                this.items.push(new CostItem(`${m.model}: $${m.total_cost?.toFixed(4)} (${m.call_count} calls)`, 'model'));
            }
        }
    }
    getTreeItem(element) { return element; }
    getChildren() { return this.items; }
}
class CostItem extends vscode.TreeItem {
    constructor(label, type) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.contextValue = type;
        if (type === 'header') {
            this.iconPath = new vscode.ThemeIcon('dash');
        }
        else if (type === 'model') {
            this.iconPath = new vscode.ThemeIcon('symbol-method');
        }
        else {
            this.iconPath = new vscode.ThemeIcon('graph');
        }
    }
}
// ── Traces Tree ──────────────────────────────────────────────────────────────
class TracesProvider {
    constructor(client) {
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
        this.items = [];
        this.client = client;
    }
    refresh() {
        this.loadData().then(() => this._onDidChangeTreeData.fire(undefined));
    }
    async loadData() {
        const traces = await this.client.getTraces(20);
        this.items = [];
        if (traces && Array.isArray(traces)) {
            for (const t of traces) {
                const cost = t.cost?.toFixed(4) || '0';
                const label = `${t.model} — $${cost} (${t.input_tokens}→${t.output_tokens} tok)`;
                this.items.push(new TraceItem(label, t));
            }
        }
    }
    getTreeItem(element) { return element; }
    getChildren() { return this.items; }
}
class TraceItem extends vscode.TreeItem {
    constructor(label, trace) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.tooltip = `Project: ${trace.project}\nModel: ${trace.model}\nLatency: ${trace.latency_ms}ms`;
        this.iconPath = trace.status === 'success'
            ? new vscode.ThemeIcon('check', new vscode.ThemeColor('testing.iconPassed'))
            : new vscode.ThemeIcon('error', new vscode.ThemeColor('testing.iconFailed'));
    }
}
// ── Budgets Tree ─────────────────────────────────────────────────────────────
class BudgetsProvider {
    constructor(client) {
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
        this.items = [];
        this.client = client;
    }
    refresh() {
        this.loadData().then(() => this._onDidChangeTreeData.fire(undefined));
    }
    async loadData() {
        const budgets = await this.client.getBudgets();
        this.items = [];
        if (budgets && Array.isArray(budgets)) {
            for (const b of budgets) {
                const pct = b.limit_usd > 0 ? (b.spent_usd / b.limit_usd * 100).toFixed(0) : '—';
                const label = `${b.project}: $${b.spent_usd?.toFixed(2)} / $${b.limit_usd} (${pct}%)`;
                this.items.push(new BudgetItem(label, b));
            }
        }
    }
    getTreeItem(element) { return element; }
    getChildren() { return this.items; }
}
class BudgetItem extends vscode.TreeItem {
    constructor(label, budget) {
        super(label, vscode.TreeItemCollapsibleState.None);
        const pct = budget.limit_usd > 0 ? budget.spent_usd / budget.limit_usd : 0;
        this.iconPath = pct > 0.9
            ? new vscode.ThemeIcon('warning', new vscode.ThemeColor('editorWarning.foreground'))
            : pct > 0.7
                ? new vscode.ThemeIcon('info', new vscode.ThemeColor('editorInfo.foreground'))
                : new vscode.ThemeIcon('shield');
    }
}
// ── Inline Cost Hints ────────────────────────────────────────────────────────
const COST_PATTERNS = [
    // Python: client.chat.completions.create(model="gpt-4o"
    /\.chat\.completions\.create\s*\(\s*model\s*=\s*["']([^"']+)["']/g,
    // Python: llm = ChatOpenAI(model="gpt-4o"
    /ChatOpenAI\s*\(\s*model\s*=\s*["']([^"']+)["']/g,
    // JS/TS: model: "gpt-4o"
    /model:\s*["']([^"']+)["']/g,
];
const MODEL_COSTS = {
    'gpt-4o': '~$2.50/1M input',
    'gpt-4o-mini': '~$0.15/1M input',
    'gpt-4-turbo': '~$10/1M input',
    'claude-3-5-sonnet': '~$3/1M input',
    'claude-3-haiku': '~$0.25/1M input',
    'llama3:8b': '$0 (local)',
};
function updateInlineCosts(editor, decorationType) {
    const config = vscode.workspace.getConfiguration('agentcost');
    if (!config.get('showInlineCosts', true))
        return;
    const text = editor.document.getText();
    const decorations = [];
    for (const pattern of COST_PATTERNS) {
        pattern.lastIndex = 0;
        let match;
        while ((match = pattern.exec(text)) !== null) {
            const model = match[1];
            const costHint = MODEL_COSTS[model];
            if (costHint) {
                const pos = editor.document.positionAt(match.index + match[0].length);
                decorations.push({
                    range: new vscode.Range(pos, pos),
                    renderOptions: {
                        after: {
                            contentText: `  💰 ${costHint}`,
                            color: new vscode.ThemeColor('editorCodeLens.foreground'),
                            fontStyle: 'italic',
                        }
                    }
                });
            }
        }
    }
    editor.setDecorations(decorationType, decorations);
}
// ── Extension Activation ─────────────────────────────────────────────────────
function activate(context) {
    const client = new AgentCostClient();
    // Register tree views
    const summaryProvider = new CostSummaryProvider(client);
    const tracesProvider = new TracesProvider(client);
    const budgetsProvider = new BudgetsProvider(client);
    vscode.window.registerTreeDataProvider('agentcost.summary', summaryProvider);
    vscode.window.registerTreeDataProvider('agentcost.traces', tracesProvider);
    vscode.window.registerTreeDataProvider('agentcost.budgets', budgetsProvider);
    // Register commands
    context.subscriptions.push(vscode.commands.registerCommand('agentcost.refreshSummary', () => {
        summaryProvider.refresh();
        tracesProvider.refresh();
        budgetsProvider.refresh();
    }), vscode.commands.registerCommand('agentcost.showTraces', () => tracesProvider.refresh()), vscode.commands.registerCommand('agentcost.configure', () => {
        vscode.commands.executeCommand('workbench.action.openSettings', 'agentcost');
    }));
    // Inline cost hints
    const decorationType = vscode.window.createTextEditorDecorationType({});
    if (vscode.window.activeTextEditor) {
        updateInlineCosts(vscode.window.activeTextEditor, decorationType);
    }
    vscode.window.onDidChangeActiveTextEditor(editor => {
        if (editor)
            updateInlineCosts(editor, decorationType);
    }, null, context.subscriptions);
    vscode.workspace.onDidChangeTextDocument(event => {
        const editor = vscode.window.activeTextEditor;
        if (editor && event.document === editor.document) {
            updateInlineCosts(editor, decorationType);
        }
    }, null, context.subscriptions);
    // Auto-refresh
    const interval = vscode.workspace.getConfiguration('agentcost').get('refreshInterval', 30);
    const timer = setInterval(() => {
        summaryProvider.refresh();
        tracesProvider.refresh();
        budgetsProvider.refresh();
    }, interval * 1000);
    context.subscriptions.push({ dispose: () => clearInterval(timer) });
    // Initial load
    summaryProvider.refresh();
    tracesProvider.refresh();
    budgetsProvider.refresh();
    vscode.window.showInformationMessage('AgentCost extension activated');
}
function deactivate() { }
//# sourceMappingURL=extension.js.map