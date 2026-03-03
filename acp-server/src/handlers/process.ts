/**
 * Process Management Handlers
 *
 * Manages long-running child processes (dev servers, background jobs, etc.)
 * with real-time output streaming to the dashboard.
 */

import { spawn, ChildProcess } from "child_process";
import { v4 as uuidv4 } from "uuid";

interface ProcessInfo {
  id: string;
  command: string;
  args: string[];
  pid?: number;
  startTime: number;
  status: "running" | "stopped" | "error";
  exitCode?: number;
  agentId?: string;
}

const processes = new Map<string, ChildProcess>();
const processInfo = new Map<string, ProcessInfo>();

export function registerProcessHandlers(server: any): void {
  /**
   * process.spawn — Start a new managed child process.
   */
  server.registerCommandHandler(
    "process.spawn",
    async (client: any, args: Record<string, any>): Promise<ProcessInfo> => {
      const { command, args: cmdArgs = [], options = {} } = args;
      if (!command) throw new Error("Missing required arg: command");

      const id = uuidv4();
      const agentId = client.agentId || "anonymous";

      const child = spawn(command, cmdArgs, {
        cwd: options.cwd || process.env.SANDBOX_CWD || "/tmp/clawwork-sandbox",
        env: { ...process.env, ...options.env },
        detached: options.detached || false,
        shell: options.shell ?? true,
      });

      const info: ProcessInfo = {
        id,
        command,
        args: cmdArgs,
        pid: child.pid,
        startTime: Date.now(),
        status: "running",
        agentId,
      };

      processes.set(id, child);
      processInfo.set(id, info);

      // Stream stdout/stderr to dashboard
      child.stdout?.on("data", (data) => {
        server.broadcastDashboard("process:stdout", {
          processId: id,
          agentId,
          data: data.toString(),
        });
      });

      child.stderr?.on("data", (data) => {
        server.broadcastDashboard("process:stderr", {
          processId: id,
          agentId,
          data: data.toString(),
        });
      });

      child.on("exit", (code, signal) => {
        info.status = code === 0 ? "stopped" : "error";
        info.exitCode = code ?? undefined;
        processes.delete(id);
        server.broadcastDashboard("process:exit", {
          processId: id,
          agentId,
          exitCode: code,
          signal,
        });
      });

      child.on("error", (err) => {
        info.status = "error";
        server.broadcastDashboard("process:error", {
          processId: id,
          agentId,
          error: err.message,
        });
      });

      console.log(`[Process] Spawned ${id}: ${command} ${cmdArgs.join(" ")} (PID ${child.pid})`);
      server.broadcastDashboard("process:started", { processId: id, agentId, command, pid: child.pid });

      return info;
    }
  );

  /**
   * process.list — List all managed processes.
   */
  server.registerCommandHandler(
    "process.list",
    async (client: any, args: Record<string, any>) => {
      const agentId = args.agentId || client.agentId;
      let infos = [...processInfo.values()];
      if (agentId) {
        infos = infos.filter((p) => p.agentId === agentId);
      }
      return infos;
    }
  );

  /**
   * process.kill — Kill a running process.
   */
  server.registerCommandHandler(
    "process.kill",
    async (_client: any, args: Record<string, any>) => {
      const { processId, signal = "SIGTERM" } = args;
      const child = processes.get(processId);
      const info = processInfo.get(processId);
      if (!child || !info) return { success: false, error: "Process not found" };

      try {
        child.kill(signal as NodeJS.Signals);
        return { success: true };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  /**
   * process.kill_all — Kill all processes (optionally filtered by agent).
   */
  server.registerCommandHandler(
    "process.kill_all",
    async (client: any, args: Record<string, any>) => {
      const agentId = args.agentId || client.agentId;
      let killed = 0;
      for (const [id, child] of processes.entries()) {
        const info = processInfo.get(id);
        if (!agentId || info?.agentId === agentId) {
          try {
            child.kill("SIGTERM");
            killed++;
          } catch { /* already dead */ }
        }
      }
      return { killed };
    }
  );

  /**
   * process.stats — Get process counts by status.
   */
  server.registerCommandHandler(
    "process.stats",
    async () => {
      const all = [...processInfo.values()];
      return {
        running: all.filter((p) => p.status === "running").length,
        stopped: all.filter((p) => p.status === "stopped").length,
        error: all.filter((p) => p.status === "error").length,
        total: all.length,
      };
    }
  );
}
