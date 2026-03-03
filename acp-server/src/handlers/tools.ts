/**
 * ClawWork Tool Handlers
 *
 * Registers ACP command handlers for each of ClawWork's 8 agent tools:
 *   file.create, file.read, search.web
 *
 * bash.execute and bash.execute_code are handled by handlers/bash.ts.
 * process.* commands are handled by handlers/process.ts.
 * Economic tools (decide_activity, submit_work, learn, get_status) stay in
 * the Python ClawWork agent — they don't need remote execution.
 */

import * as fs from "fs";
import * as path from "path";

export function registerToolHandlers(server: any): void {
  const WORKSPACE = process.env.SANDBOX_CWD || "/tmp/clawwork-sandbox";

  // Ensure workspace exists
  fs.mkdirSync(WORKSPACE, { recursive: true });

  /**
   * file.create — Create a file in the sandbox workspace.
   *
   * Args: { filename: string, content: string, cwd?: string, file_type?: string }
   */
  server.registerCommandHandler(
    "file.create",
    async (client: any, args: Record<string, any>) => {
      const { filename, content, cwd, file_type } = args;
      if (!filename) throw new Error("Missing required arg: filename");
      if (content === undefined) throw new Error("Missing required arg: content");

      const dir = cwd || WORKSPACE;
      fs.mkdirSync(dir, { recursive: true });

      const filepath = path.resolve(dir, filename);
      // Security: prevent path traversal outside workspace
      if (!filepath.startsWith(path.resolve(WORKSPACE))) {
        throw new Error("Path traversal outside workspace is not allowed");
      }

      // Create parent directories if needed
      fs.mkdirSync(path.dirname(filepath), { recursive: true });
      fs.writeFileSync(filepath, content, "utf-8");

      const stats = fs.statSync(filepath);

      console.log(`[Tools] Created file: ${filepath} (${stats.size} bytes)`);
      server.broadcastDashboard("file:created", {
        agentId: client.agentId,
        filename,
        filepath,
        size: stats.size,
        fileType: file_type || path.extname(filename),
      });

      return {
        filepath,
        filename,
        size: stats.size,
        created: true,
      };
    }
  );

  /**
   * file.read — Read a file from the sandbox workspace.
   *
   * Args: { filepath: string }
   */
  server.registerCommandHandler(
    "file.read",
    async (_client: any, args: Record<string, any>) => {
      const { filepath } = args;
      if (!filepath) throw new Error("Missing required arg: filepath");

      const resolved = path.resolve(WORKSPACE, filepath);
      if (!resolved.startsWith(path.resolve(WORKSPACE))) {
        throw new Error("Path traversal outside workspace is not allowed");
      }
      if (!fs.existsSync(resolved)) {
        throw new Error(`File not found: ${filepath}`);
      }

      const content = fs.readFileSync(resolved, "utf-8");
      const stats = fs.statSync(resolved);

      return {
        filepath: resolved,
        content,
        size: stats.size,
      };
    }
  );

  /**
   * file.list — List files in the workspace.
   *
   * Args: { dir?: string, pattern?: string }
   */
  server.registerCommandHandler(
    "file.list",
    async (_client: any, args: Record<string, any>) => {
      const dir = path.resolve(WORKSPACE, args.dir || ".");
      if (!dir.startsWith(path.resolve(WORKSPACE))) {
        throw new Error("Path traversal outside workspace is not allowed");
      }
      if (!fs.existsSync(dir)) return { files: [] };

      const entries = fs.readdirSync(dir, { withFileTypes: true });
      return {
        files: entries.map((e) => ({
          name: e.name,
          type: e.isDirectory() ? "directory" : "file",
          path: path.join(dir, e.name),
        })),
      };
    }
  );

  /**
   * search.web — Proxy web search (delegates to Tavily or Jina).
   *
   * Args: { query: string, max_results?: number }
   */
  server.registerCommandHandler(
    "search.web",
    async (client: any, args: Record<string, any>) => {
      const { query, max_results = 5 } = args;
      if (!query) throw new Error("Missing required arg: query");

      const provider = process.env.WEB_SEARCH_PROVIDER || "tavily";
      const apiKey = process.env.WEB_SEARCH_API_KEY;

      if (!apiKey) {
        return {
          results: [],
          error: "WEB_SEARCH_API_KEY not configured on ACP server",
        };
      }

      try {
        let results: any[];

        if (provider === "tavily") {
          const resp = await fetch("https://api.tavily.com/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              api_key: apiKey,
              query,
              max_results,
              search_depth: "basic",
            }),
          });
          const data = await resp.json();
          results = (data.results || []).map((r: any) => ({
            title: r.title,
            url: r.url,
            snippet: r.content,
          }));
        } else if (provider === "jina") {
          const resp = await fetch(
            `https://s.jina.ai/${encodeURIComponent(query)}`,
            {
              headers: {
                Authorization: `Bearer ${apiKey}`,
                Accept: "application/json",
              },
            }
          );
          const data = await resp.json();
          results = (data.data || []).slice(0, max_results).map((r: any) => ({
            title: r.title,
            url: r.url,
            snippet: r.description,
          }));
        } else {
          throw new Error(`Unsupported search provider: ${provider}`);
        }

        server.broadcastDashboard("search:completed", {
          agentId: client.agentId,
          query,
          resultCount: results.length,
        });

        return { results, query, provider };
      } catch (err: any) {
        return { results: [], query, error: err.message };
      }
    }
  );
}
