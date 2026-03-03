/**
 * ClawWork ACP Server
 *
 * Unified execution gateway that replaces E2B cloud sandboxes with self-hosted
 * command execution, process management, file creation, and real-time dashboard
 * streaming — all over the Agent Client Protocol.
 */

import WebSocket, { WebSocketServer } from "ws";
import { v4 as uuidv4 } from "uuid";
import { registerBashHandlers } from "./handlers/bash";
import { registerProcessHandlers } from "./handlers/process";
import { registerToolHandlers } from "./handlers/tools";
import { registerDashboardHandlers } from "./handlers/dashboard";
import { registerAgentHandlers } from "./handlers/agents";
import "dotenv/config";

// ── Types ───────────────────────────────────────────────────────────────────

interface ACPMessage {
  id: string;
  type: "command" | "response" | "event" | "error";
  timestamp: number;
  [key: string]: any;
}

interface ClientConnection {
  id: string;
  ws: WebSocket;
  role: "agent" | "dashboard" | "unknown";
  agentId?: string;
  connectedAt: number;
  authenticated: boolean;
}

type CommandHandler = (
  client: ClientConnection,
  args: Record<string, any>
) => Promise<any>;

// ── Server ──────────────────────────────────────────────────────────────────

export class ClawWorkACPServer {
  private wss: WebSocketServer | null = null;
  private clients = new Map<string, ClientConnection>();
  private handlers = new Map<string, CommandHandler>();

  // Shared state accessible by handlers
  public agentRegistry = new Map<
    string,
    { id: string; status: string; balance: number; connectedAt: number }
  >();

  constructor(
    private port: number = Number(process.env.ACP_PORT) || 8080,
    private host: string = process.env.ACP_HOST || "127.0.0.1"
  ) {}

  // ── Lifecycle ───────────────────────────────────────────────────────

  start(): void {
    this.wss = new WebSocketServer({ port: this.port, host: this.host });

    this.wss.on("connection", (ws, req) =>
      this.handleConnection(ws, req)
    );

    this.wss.on("error", (err) => console.error("[ACP] Server error:", err));

    // Register all handler groups
    registerBashHandlers(this);
    registerProcessHandlers(this);
    registerToolHandlers(this);
    registerDashboardHandlers(this);
    registerAgentHandlers(this);

    console.log(`\n🦞 ClawWork ACP Server listening on ws://${this.host}:${this.port}`);
    console.log(`   Registered commands: ${[...this.handlers.keys()].join(", ")}\n`);
  }

  stop(): void {
    for (const c of this.clients.values()) c.ws.close(1000, "Server stopping");
    this.clients.clear();
    this.wss?.close(() => console.log("[ACP] Server stopped"));
    this.wss = null;
  }

  // ── Public API for handlers ───────────────────────────────────────

  registerCommandHandler(command: string, handler: CommandHandler): void {
    this.handlers.set(command, handler);
  }

  /** Broadcast a JSON message to all connected dashboard clients. */
  broadcastDashboard(event: string, data: any): void {
    const msg = JSON.stringify({
      id: uuidv4(),
      type: "event",
      event,
      data,
      timestamp: Date.now(),
    });
    for (const c of this.clients.values()) {
      if (c.role === "dashboard" && c.ws.readyState === WebSocket.OPEN) {
        c.ws.send(msg);
      }
    }
  }

  /** Broadcast to all connected clients regardless of role. */
  broadcast(message: any): void {
    const raw = JSON.stringify(message);
    for (const c of this.clients.values()) {
      if (c.ws.readyState === WebSocket.OPEN) c.ws.send(raw);
    }
  }

  /** Send a message to a specific agent by agentId. */
  sendToAgent(agentId: string, message: any): boolean {
    for (const c of this.clients.values()) {
      if (c.agentId === agentId && c.ws.readyState === WebSocket.OPEN) {
        c.ws.send(JSON.stringify(message));
        return true;
      }
    }
    return false;
  }

  getConnectedAgents(): string[] {
    return [...this.clients.values()]
      .filter((c) => c.role === "agent" && c.agentId)
      .map((c) => c.agentId!);
  }

  getClients(): ClientConnection[] {
    return [...this.clients.values()];
  }

  // ── Internal ──────────────────────────────────────────────────────

  private handleConnection(ws: WebSocket, req: any): void {
    const clientId = uuidv4();
    const url = new URL(req.url || "/", `http://${this.host}`);
    const role = (url.searchParams.get("role") as any) || "unknown";
    const agentId = url.searchParams.get("agentId") || undefined;

    const client: ClientConnection = {
      id: clientId,
      ws,
      role,
      agentId,
      connectedAt: Date.now(),
      authenticated: true, // simplified; add real auth via middleware
    };

    this.clients.set(clientId, client);
    console.log(
      `[ACP] Client connected: ${clientId} role=${role}` +
        (agentId ? ` agent=${agentId}` : "") +
        ` (${this.clients.size} total)`
    );

    if (role === "agent" && agentId) {
      this.agentRegistry.set(agentId, {
        id: agentId,
        status: "connected",
        balance: 0,
        connectedAt: Date.now(),
      });
      this.broadcastDashboard("agent:connected", { agentId });
    }

    ws.on("message", (raw) => this.handleMessage(client, raw));
    ws.on("close", () => this.handleDisconnect(client));
    ws.on("error", (err) =>
      console.error(`[ACP] Client ${clientId} error:`, err.message)
    );

    // Keepalive
    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.ping();
      else clearInterval(ping);
    }, 30_000);
  }

  private async handleMessage(
    client: ClientConnection,
    raw: WebSocket.Data
  ): Promise<void> {
    let msg: ACPMessage;
    try {
      msg = JSON.parse(raw.toString());
    } catch {
      return this.sendError(client, "Invalid JSON");
    }

    if (msg.type !== "command") return;

    const handler = this.handlers.get(msg.command);
    if (!handler) {
      return this.sendResponse(client, msg.id, false, undefined,
        `Unknown command: ${msg.command}`);
    }

    try {
      const result = await handler(client, msg.args || {});
      this.sendResponse(client, msg.id, true, result);
    } catch (err: any) {
      console.error(`[ACP] Command error ${msg.command}:`, err.message);
      this.sendResponse(client, msg.id, false, undefined, err.message);
    }
  }

  private sendResponse(
    client: ClientConnection,
    requestId: string,
    success: boolean,
    data?: any,
    error?: string
  ): void {
    if (client.ws.readyState !== WebSocket.OPEN) return;
    client.ws.send(
      JSON.stringify({
        id: uuidv4(),
        type: "response",
        requestId,
        success,
        data,
        error,
        timestamp: Date.now(),
      })
    );
  }

  private sendError(client: ClientConnection, error: string): void {
    if (client.ws.readyState !== WebSocket.OPEN) return;
    client.ws.send(
      JSON.stringify({ id: uuidv4(), type: "error", error, timestamp: Date.now() })
    );
  }

  private handleDisconnect(client: ClientConnection): void {
    this.clients.delete(client.id);
    if (client.role === "agent" && client.agentId) {
      const info = this.agentRegistry.get(client.agentId);
      if (info) info.status = "disconnected";
      this.broadcastDashboard("agent:disconnected", {
        agentId: client.agentId,
      });
    }
    console.log(
      `[ACP] Client disconnected: ${client.id} (${this.clients.size} remaining)`
    );
  }
}

// ── Bootstrap ───────────────────────────────────────────────────────────────

if (require.main === module) {
  const server = new ClawWorkACPServer();
  server.start();

  process.on("SIGINT", () => {
    console.log("\nShutting down …");
    server.stop();
    process.exit(0);
  });
}
