import * as vscode from 'vscode';

// ── AgentCost API Client ─────────────────────────────────────────────────────

class AgentCostClient {
  private endpoint: string;
  private apiKey: string;

  constructor() {
    const config = vscode.workspace.getConfiguration('agentcost');
    this.endpoint = config.get('endpoint', 'http://localhost:8100');
    this.apiKey = config.get('apiKey', '');
  }

  private async fetch(path: string): Promise<any> {
    const url = `${this.endpoint}${path}`;
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.apiKey) headers['X-API-Key'] = this.apiKey;

    try {
      const resp = await fetch(url, { headers });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e: any) {
      vscode.window.showWarningMessage(`AgentCost: ${e.message}`);
      return null;
    }
  }

  async getSummary(): Promise<any> { return this.fetch('/api/summary'); }
  async getTraces(limit = 20): Promise<any> { return this.fetch(`/api/traces?limit=${limit}`); }
  async getBudgets(): Promise<any> { return this.fetch('/api/budgets'); }
  async getCostByModel(): Promise<any> { return this.fetch('/api/cost/by-model'); }
}

// ── Cost Summary Tree ────────────────────────────────────────────────────────

class CostSummaryProvider implements vscode.TreeDataProvider<CostItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<CostItem | undefined>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
  private client: AgentCostClient;
  private items: CostItem[] = [];

  constructor(client: AgentCostClient) { this.client = client; }

  refresh(): void {
    this.loadData().then(() => this._onDidChangeTreeData.fire(undefined));
  }

  private async loadData(): Promise<void> {
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
        this.items.push(new CostItem(
          `${m.model}: $${m.total_cost?.toFixed(4)} (${m.call_count} calls)`, 'model'
        ));
      }
    }
  }

  getTreeItem(element: CostItem): vscode.TreeItem { return element; }
  getChildren(): CostItem[] { return this.items; }
}

class CostItem extends vscode.TreeItem {
  constructor(label: string, type: string) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.contextValue = type;
    if (type === 'header') {
      this.iconPath = new vscode.ThemeIcon('dash');
    } else if (type === 'model') {
      this.iconPath = new vscode.ThemeIcon('symbol-method');
    } else {
      this.iconPath = new vscode.ThemeIcon('graph');
    }
  }
}

// ── Traces Tree ──────────────────────────────────────────────────────────────

class TracesProvider implements vscode.TreeDataProvider<TraceItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<TraceItem | undefined>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
  private client: AgentCostClient;
  private items: TraceItem[] = [];

  constructor(client: AgentCostClient) { this.client = client; }

  refresh(): void {
    this.loadData().then(() => this._onDidChangeTreeData.fire(undefined));
  }

  private async loadData(): Promise<void> {
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

  getTreeItem(element: TraceItem): vscode.TreeItem { return element; }
  getChildren(): TraceItem[] { return this.items; }
}

class TraceItem extends vscode.TreeItem {
  constructor(label: string, trace: any) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.tooltip = `Project: ${trace.project}\nModel: ${trace.model}\nLatency: ${trace.latency_ms}ms`;
    this.iconPath = trace.status === 'success'
      ? new vscode.ThemeIcon('check', new vscode.ThemeColor('testing.iconPassed'))
      : new vscode.ThemeIcon('error', new vscode.ThemeColor('testing.iconFailed'));
  }
}

// ── Budgets Tree ─────────────────────────────────────────────────────────────

class BudgetsProvider implements vscode.TreeDataProvider<BudgetItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<BudgetItem | undefined>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
  private client: AgentCostClient;
  private items: BudgetItem[] = [];

  constructor(client: AgentCostClient) { this.client = client; }

  refresh(): void {
    this.loadData().then(() => this._onDidChangeTreeData.fire(undefined));
  }

  private async loadData(): Promise<void> {
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

  getTreeItem(element: BudgetItem): vscode.TreeItem { return element; }
  getChildren(): BudgetItem[] { return this.items; }
}

class BudgetItem extends vscode.TreeItem {
  constructor(label: string, budget: any) {
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

const MODEL_COSTS: Record<string, string> = {
  'gpt-4o': '~$2.50/1M input',
  'gpt-4o-mini': '~$0.15/1M input',
  'gpt-4-turbo': '~$10/1M input',
  'claude-3-5-sonnet': '~$3/1M input',
  'claude-3-haiku': '~$0.25/1M input',
  'llama3:8b': '$0 (local)',
};

function updateInlineCosts(editor: vscode.TextEditor, decorationType: vscode.TextEditorDecorationType) {
  const config = vscode.workspace.getConfiguration('agentcost');
  if (!config.get('showInlineCosts', true)) return;

  const text = editor.document.getText();
  const decorations: vscode.DecorationOptions[] = [];

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

export function activate(context: vscode.ExtensionContext) {
  const client = new AgentCostClient();

  // Register tree views
  const summaryProvider = new CostSummaryProvider(client);
  const tracesProvider = new TracesProvider(client);
  const budgetsProvider = new BudgetsProvider(client);

  vscode.window.registerTreeDataProvider('agentcost.summary', summaryProvider);
  vscode.window.registerTreeDataProvider('agentcost.traces', tracesProvider);
  vscode.window.registerTreeDataProvider('agentcost.budgets', budgetsProvider);

  // Register commands
  context.subscriptions.push(
    vscode.commands.registerCommand('agentcost.refreshSummary', () => {
      summaryProvider.refresh();
      tracesProvider.refresh();
      budgetsProvider.refresh();
    }),
    vscode.commands.registerCommand('agentcost.showTraces', () => tracesProvider.refresh()),
    vscode.commands.registerCommand('agentcost.configure', () => {
      vscode.commands.executeCommand('workbench.action.openSettings', 'agentcost');
    })
  );

  // Inline cost hints
  const decorationType = vscode.window.createTextEditorDecorationType({});
  if (vscode.window.activeTextEditor) {
    updateInlineCosts(vscode.window.activeTextEditor, decorationType);
  }
  vscode.window.onDidChangeActiveTextEditor(editor => {
    if (editor) updateInlineCosts(editor, decorationType);
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

export function deactivate() {}
