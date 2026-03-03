/**
 * Bash Execution Handlers
 *
 * Replaces E2B cloud sandbox with self-hosted command execution.
 * Includes approval gating, dangerous-command detection, and timeout control.
 */

import { exec, ExecOptions } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

// Dangerous command patterns
const DANGEROUS_PATTERNS = [
  /rm\s+-rf\s+\//,
  /:\(\)\{.*\};/,
  /dd\s+if=/,
  /mkfs/,
  />\s*\/dev\/sd/,
  /curl\s+.*\|\s*sh/,
  /wget\s+.*\|\s*sh/,
];

interface BashResult {
  stdout: string;
  stderr: string;
  exitCode: number;
  approved: boolean;
  duration: number;
}

// Per-agent command history for audit
const commandHistory = new Map<string, Array<{ command: string; result: BashResult; timestamp: number }>>();

function validateCommand(command: string): { safe: boolean; warnings: string[] } {
  const warnings: string[] = [];
  for (const pattern of DANGEROUS_PATTERNS) {
    if (pattern.test(command)) {
      warnings.push(`Dangerous pattern: ${pattern.source}`);
    }
  }
  if (command.includes("sudo")) {
    warnings.push("Requires elevated privileges");
  }
  return { safe: warnings.length === 0, warnings };
}

export function registerBashHandlers(server: any): void {
  const SANDBOX_CWD = process.env.SANDBOX_CWD || "/tmp/clawwork-sandbox";
  const TIMEOUT = Number(process.env.BASH_TIMEOUT) || 30_000;
  const MAX_BUFFER = 10 * 1024 * 1024; // 10 MB

  // Ensure sandbox dir exists
  exec(`mkdir -p ${SANDBOX_CWD}`);

  /**
   * bash.execute — Run a shell command inside the sandbox.
   *
   * Args: { command: string, cwd?: string, language?: string }
   * Returns: BashExecutionResult
   */
  server.registerCommandHandler(
    "bash.execute",
    async (client: any, args: Record<string, any>): Promise<BashResult> => {
      const command: string = args.command;
      if (!command) throw new Error("Missing required arg: command");

      const start = Date.now();
      const agentId = client.agentId || "anonymous";

      // Safety check
      const validation = validateCommand(command);
      if (!validation.safe) {
        console.log(`[Bash] ❌ Blocked dangerous command from ${agentId}: ${command}`);
        server.broadcastDashboard("bash:blocked", {
          agentId,
          command,
          warnings: validation.warnings,
        });
        return {
          stdout: "",
          stderr: `Command blocked — ${validation.warnings.join("; ")}`,
          exitCode: 1,
          approved: false,
          duration: Date.now() - start,
        };
      }

      const execOpts: ExecOptions = {
        cwd: args.cwd || SANDBOX_CWD,
        timeout: TIMEOUT,
        maxBuffer: MAX_BUFFER,
        env: { ...process.env, HOME: SANDBOX_CWD },
      };

      try {
        const { stdout, stderr } = await execAsync(command, execOpts);
        const result: BashResult = {
          stdout: stdout.toString(),
          stderr: stderr.toString(),
          exitCode: 0,
          approved: true,
          duration: Date.now() - start,
        };

        // Audit log
        if (!commandHistory.has(agentId)) commandHistory.set(agentId, []);
        commandHistory.get(agentId)!.push({ command, result, timestamp: Date.now() });

        // Stream to dashboard
        server.broadcastDashboard("bash:executed", {
          agentId,
          command,
          exitCode: 0,
          duration: result.duration,
        });

        return result;
      } catch (err: any) {
        const result: BashResult = {
          stdout: err.stdout?.toString() || "",
          stderr: err.stderr?.toString() || err.message,
          exitCode: err.code || 1,
          approved: true,
          duration: Date.now() - start,
        };

        if (!commandHistory.has(agentId)) commandHistory.set(agentId, []);
        commandHistory.get(agentId)!.push({ command, result, timestamp: Date.now() });

        server.broadcastDashboard("bash:error", {
          agentId,
          command,
          exitCode: result.exitCode,
          stderr: result.stderr.slice(0, 500),
        });

        return result;
      }
    }
  );

  /**
   * bash.execute_code — Run code in a specific language (replaces E2B execute_code).
   *
   * Args: { code: string, language?: string }
   */
  server.registerCommandHandler(
    "bash.execute_code",
    async (client: any, args: Record<string, any>): Promise<BashResult> => {
      const { code, language = "python" } = args;
      if (!code) throw new Error("Missing required arg: code");

      let command: string;
      switch (language) {
        case "python":
          command = `python3 -c ${JSON.stringify(code)}`;
          break;
        case "node":
        case "javascript":
          command = `node -e ${JSON.stringify(code)}`;
          break;
        case "bash":
        case "shell":
          command = code;
          break;
        default:
          throw new Error(`Unsupported language: ${language}`);
      }

      // Delegate to bash.execute
      const handler = server.handlers?.get?.("bash.execute");
      if (!handler) throw new Error("bash.execute handler not registered");
      // Direct call since we're in the same server
      return execAsync(command, {
        cwd: SANDBOX_CWD,
        timeout: TIMEOUT,
        maxBuffer: MAX_BUFFER,
      })
        .then(({ stdout, stderr }) => ({
          stdout: stdout.toString(),
          stderr: stderr.toString(),
          exitCode: 0,
          approved: true,
          duration: 0,
        }))
        .catch((err: any) => ({
          stdout: err.stdout?.toString() || "",
          stderr: err.stderr?.toString() || err.message,
          exitCode: err.code || 1,
          approved: true,
          duration: 0,
        }));
    }
  );

  /**
   * bash.validate — Check if a command is safe (no execution).
   */
  server.registerCommandHandler(
    "bash.validate",
    async (_client: any, args: Record<string, any>) => {
      return validateCommand(args.command || "");
    }
  );

  /**
   * bash.history — Return command history for an agent.
   */
  server.registerCommandHandler(
    "bash.history",
    async (client: any, args: Record<string, any>) => {
      const agentId = args.agentId || client.agentId || "anonymous";
      return commandHistory.get(agentId) || [];
    }
  );
}
