/**
 * Dashboard Handlers
 *
 * Replaces ClawWork's separate FastAPI + WebSocket dashboard server with
 * unified ACP commands. The React frontend connects as a "dashboard" role
 * client and receives broadcasts for every agent action.
 */

export function registerDashboardHandlers(server: any): void {
  /**
   * dashboard.subscribe — Mark this client as a dashboard subscriber.
   * (Role is already set via ?role=dashboard query param, but this allows
   *  explicit subscription from any client.)
   */
  server.registerCommandHandler(
    "dashboard.subscribe",
    async (client: any, _args: Record<string, any>) => {
      client.role = "dashboard";
      return { subscribed: true };
    }
  );

  /**
   * dashboard.agents — Get all registered agents and their status.
   */
  server.registerCommandHandler(
    "dashboard.agents",
    async () => {
      return [...server.agentRegistry.values()];
    }
  );

  /**
   * dashboard.stats — Aggregate server statistics.
   */
  server.registerCommandHandler(
    "dashboard.stats",
    async () => {
      const clients = server.getClients();
      const agents = server.getConnectedAgents();
      return {
        totalClients: clients.length,
        agentClients: clients.filter((c: any) => c.role === "agent").length,
        dashboardClients: clients.filter((c: any) => c.role === "dashboard").length,
        connectedAgents: agents,
        registeredAgents: [...server.agentRegistry.keys()],
        uptime: process.uptime(),
      };
    }
  );

  /**
   * dashboard.broadcast — Let the dashboard send a message to all agents.
   */
  server.registerCommandHandler(
    "dashboard.broadcast",
    async (_client: any, args: Record<string, any>) => {
      const { event, data } = args;
      server.broadcast({
        id: require("uuid").v4(),
        type: "event",
        event: event || "dashboard:message",
        data,
        timestamp: Date.now(),
      });
      return { sent: true };
    }
  );
}
