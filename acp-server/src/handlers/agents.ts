/**
 * Agent Management Handlers
 *
 * Supports multi-agent competition: register agents, update economic state,
 * query agent info, and route tasks to specific agents.
 */

export function registerAgentHandlers(server: any): void {
  /**
   * agent.register — Register a new agent with the gateway.
   */
  server.registerCommandHandler(
    "agent.register",
    async (client: any, args: Record<string, any>) => {
      const { agentId, model, initialBalance = 10.0, config = {} } = args;
      if (!agentId) throw new Error("Missing required arg: agentId");

      client.agentId = agentId;
      client.role = "agent";

      server.agentRegistry.set(agentId, {
        id: agentId,
        model,
        status: "active",
        balance: initialBalance,
        connectedAt: Date.now(),
        config,
        stats: {
          tasksCompleted: 0,
          totalIncome: 0,
          totalCost: 0,
          learningEntries: 0,
        },
      });

      console.log(`[Agent] Registered: ${agentId} (model=${model}, balance=$${initialBalance})`);
      server.broadcastDashboard("agent:registered", {
        agentId,
        model,
        balance: initialBalance,
      });

      return { registered: true, agentId, balance: initialBalance };
    }
  );

  /**
   * agent.info — Get agent information.
   */
  server.registerCommandHandler(
    "agent.info",
    async (client: any, args: Record<string, any>) => {
      const agentId = args.agentId || client.agentId;
      if (!agentId) throw new Error("No agentId specified");

      const info = server.agentRegistry.get(agentId);
      if (!info) throw new Error(`Agent not found: ${agentId}`);
      return info;
    }
  );

  /**
   * agent.list — List all registered agents.
   */
  server.registerCommandHandler(
    "agent.list",
    async () => {
      return [...server.agentRegistry.values()];
    }
  );

  /**
   * agent.update_balance — Update an agent's economic balance.
   * Called by the Python ClawWork agent after token usage or task payment.
   */
  server.registerCommandHandler(
    "agent.update_balance",
    async (client: any, args: Record<string, any>) => {
      const agentId = args.agentId || client.agentId;
      const { balance, income, cost, taskId, reason } = args;

      const info = server.agentRegistry.get(agentId);
      if (!info) throw new Error(`Agent not found: ${agentId}`);

      if (balance !== undefined) info.balance = balance;
      if (income) {
        info.stats.totalIncome += income;
        info.stats.tasksCompleted++;
      }
      if (cost) info.stats.totalCost += cost;

      // Check survival status
      const survivalStatus =
        info.balance > 100 ? "thriving" :
        info.balance > 10  ? "stable" :
        info.balance > 0   ? "struggling" :
        "bankrupt";

      info.status = survivalStatus;

      server.broadcastDashboard("agent:balance_update", {
        agentId,
        balance: info.balance,
        income,
        cost,
        taskId,
        reason,
        survivalStatus,
        stats: info.stats,
      });

      return { agentId, balance: info.balance, status: survivalStatus };
    }
  );

  /**
   * agent.submit_work — Record a completed task and its payment.
   */
  server.registerCommandHandler(
    "agent.submit_work",
    async (client: any, args: Record<string, any>) => {
      const agentId = args.agentId || client.agentId;
      const { taskId, qualityScore, payment, artifacts = [], sector, occupation } = args;

      const info = server.agentRegistry.get(agentId);
      if (!info) throw new Error(`Agent not found: ${agentId}`);

      info.balance += payment || 0;
      info.stats.totalIncome += payment || 0;
      info.stats.tasksCompleted++;

      server.broadcastDashboard("agent:task_completed", {
        agentId,
        taskId,
        qualityScore,
        payment,
        artifacts,
        sector,
        occupation,
        newBalance: info.balance,
      });

      console.log(
        `[Agent] ${agentId} completed task ${taskId}: ` +
        `quality=${qualityScore}, payment=$${payment?.toFixed(2)}, ` +
        `balance=$${info.balance.toFixed(2)}`
      );

      return {
        agentId,
        taskId,
        payment,
        balance: info.balance,
        status: info.status,
      };
    }
  );

  /**
   * agent.track_cost — Record token usage cost for an agent.
   */
  server.registerCommandHandler(
    "agent.track_cost",
    async (client: any, args: Record<string, any>) => {
      const agentId = args.agentId || client.agentId;
      const { cost, inputTokens, outputTokens, model, taskId } = args;

      const info = server.agentRegistry.get(agentId);
      if (!info) throw new Error(`Agent not found: ${agentId}`);

      info.balance -= cost || 0;
      info.stats.totalCost += cost || 0;

      server.broadcastDashboard("agent:cost_tracked", {
        agentId,
        cost,
        inputTokens,
        outputTokens,
        model,
        taskId,
        newBalance: info.balance,
      });

      return { agentId, cost, balance: info.balance };
    }
  );

  /**
   * agent.learn — Record a learning entry for an agent.
   */
  server.registerCommandHandler(
    "agent.learn",
    async (client: any, args: Record<string, any>) => {
      const agentId = args.agentId || client.agentId;
      const { topic, knowledge } = args;

      const info = server.agentRegistry.get(agentId);
      if (info) info.stats.learningEntries++;

      server.broadcastDashboard("agent:learned", {
        agentId,
        topic,
        knowledgeLength: knowledge?.length || 0,
      });

      return { recorded: true };
    }
  );
}
