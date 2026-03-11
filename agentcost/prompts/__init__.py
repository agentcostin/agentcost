"""
AgentCost Prompts — Prompt Management & Versioning.

Store, version, deploy, and track the cost of system prompts across your LLM
applications.  Every edit creates an immutable version.  Versions can be
deployed to environments (dev / staging / production).  When a trace is
tagged with a prompt_id + version, cost analytics are automatically linked —
so you can answer "did V2 of our support prompt cost more than V1?"

Usage:
    from agentcost.prompts import PromptService, get_prompt_service

    svc = get_prompt_service()

    # Create a prompt
    p = svc.create_prompt("support-bot", project="support",
                          content="You are a helpful support agent for {{product}}.")

    # New version
    v = svc.create_version("support-bot",
                           content="You are a concise support agent for {{product}}. Be brief.",
                           commit_message="shorter replies save tokens")

    # Deploy to production
    svc.deploy("support-bot", version=2, environment="production")

    # Resolve for SDK usage
    prompt = svc.resolve("support-bot", environment="production",
                         variables={"product": "AgentCost"})
    print(prompt["content"])
    # → "You are a concise support agent for AgentCost. Be brief."

CLI:
    agentcost prompt list
    agentcost prompt show support-bot
    agentcost prompt versions support-bot
    agentcost prompt deploy support-bot --version 3 --env production
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("agentcost.prompts")


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class Prompt:
    """A named prompt template."""

    id: str
    name: str
    project: str = "default"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    latest_version: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0
    org_id: str = "default"

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = time.time()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "project": self.project,
            "description": self.description,
            "tags": self.tags,
            "latest_version": self.latest_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "org_id": self.org_id,
        }


@dataclass
class PromptVersion:
    """An immutable snapshot of a prompt's content."""

    id: str
    prompt_id: str
    version: int
    content: str
    model: str = ""
    variables: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    author: str = ""
    commit_message: str = ""
    created_at: float = 0.0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()
        if not self.variables:
            self.variables = self._extract_variables()

    def _extract_variables(self) -> list[str]:
        """Extract {{variable}} placeholders from content."""
        return sorted(set(re.findall(r"\{\{(\w+)\}\}", self.content)))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "prompt_id": self.prompt_id,
            "version": self.version,
            "content": self.content,
            "model": self.model,
            "variables": self.variables,
            "config": self.config,
            "author": self.author,
            "commit_message": self.commit_message,
            "created_at": self.created_at,
        }


@dataclass
class PromptDeployment:
    """Tracks which version is active in which environment."""

    id: str
    prompt_id: str
    version_id: str
    version: int
    environment: str = "production"
    deployed_at: float = 0.0
    deployed_by: str = ""

    def __post_init__(self):
        if not self.deployed_at:
            self.deployed_at = time.time()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "prompt_id": self.prompt_id,
            "version_id": self.version_id,
            "version": self.version,
            "environment": self.environment,
            "deployed_at": self.deployed_at,
            "deployed_by": self.deployed_by,
        }


# ── Schema ───────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prompts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    project TEXT NOT NULL DEFAULT 'default',
    description TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    latest_version INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    org_id TEXT NOT NULL DEFAULT 'default'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_prompts_name_project
    ON prompts(name, project, org_id);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id TEXT PRIMARY KEY,
    prompt_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    model TEXT DEFAULT '',
    variables TEXT DEFAULT '[]',
    config TEXT DEFAULT '{}',
    author TEXT DEFAULT '',
    commit_message TEXT DEFAULT '',
    created_at REAL NOT NULL,
    UNIQUE(prompt_id, version)
);
CREATE INDEX IF NOT EXISTS idx_pv_prompt ON prompt_versions(prompt_id);

CREATE TABLE IF NOT EXISTS prompt_deployments (
    id TEXT PRIMARY KEY,
    prompt_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    environment TEXT NOT NULL DEFAULT 'production',
    deployed_at REAL NOT NULL,
    deployed_by TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pd_prompt_env
    ON prompt_deployments(prompt_id, environment);
CREATE INDEX IF NOT EXISTS idx_pd_prompt ON prompt_deployments(prompt_id);
"""


# ── Service ──────────────────────────────────────────────────────────────────


class PromptService:
    """Prompt management with versioning and deployment."""

    def __init__(self, db=None):
        from ..data.connection import get_db

        self.db = db or get_db()
        self._init()

    def _init(self):
        self.db.executescript(_SCHEMA)

    # ── Create ───────────────────────────────────────────────────

    def create_prompt(
        self,
        name: str,
        *,
        project: str = "default",
        content: str = "",
        description: str = "",
        tags: list[str] | None = None,
        model: str = "",
        config: dict | None = None,
        author: str = "",
        commit_message: str = "Initial version",
        org_id: str = "default",
    ) -> dict:
        """Create a new prompt with its first version."""
        prompt_id = str(uuid.uuid4())[:12]
        now = time.time()

        prompt = Prompt(
            id=prompt_id,
            name=name,
            project=project,
            description=description,
            tags=tags or [],
            latest_version=1,
            created_at=now,
            updated_at=now,
            org_id=org_id,
        )

        self.db.execute(
            """INSERT INTO prompts (id, name, project, description, tags,
               latest_version, created_at, updated_at, org_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                prompt.id,
                prompt.name,
                prompt.project,
                prompt.description,
                json.dumps(prompt.tags),
                prompt.latest_version,
                prompt.created_at,
                prompt.updated_at,
                prompt.org_id,
            ),
        )

        # Create V1
        version = self._create_version_record(
            prompt_id=prompt_id,
            version=1,
            content=content,
            model=model,
            config=config or {},
            author=author,
            commit_message=commit_message,
        )

        result = prompt.to_dict()
        result["active_version"] = version
        logger.info("Created prompt '%s' (id=%s) with V1", name, prompt_id)
        return result

    # ── Versions ─────────────────────────────────────────────────

    def create_version(
        self,
        prompt_id: str,
        *,
        content: str,
        model: str = "",
        config: dict | None = None,
        author: str = "",
        commit_message: str = "",
    ) -> dict:
        """Create a new version of an existing prompt."""
        prompt = self._get_prompt_row(prompt_id)
        if not prompt:
            # Try by name
            prompt = self._get_prompt_by_name(prompt_id)
        if not prompt:
            raise ValueError(f"Prompt not found: {prompt_id}")

        pid = prompt["id"]
        new_version = prompt["latest_version"] + 1

        version = self._create_version_record(
            prompt_id=pid,
            version=new_version,
            content=content,
            model=model,
            config=config or {},
            author=author,
            commit_message=commit_message,
        )

        now = time.time()
        self.db.execute(
            "UPDATE prompts SET latest_version=?, updated_at=? WHERE id=?",
            (new_version, now, pid),
        )

        logger.info("Created V%d for prompt %s", new_version, pid)
        return version

    def _create_version_record(
        self,
        *,
        prompt_id: str,
        version: int,
        content: str,
        model: str,
        config: dict,
        author: str,
        commit_message: str,
    ) -> dict:
        vid = str(uuid.uuid4())[:12]
        pv = PromptVersion(
            id=vid,
            prompt_id=prompt_id,
            version=version,
            content=content,
            model=model,
            config=config,
            author=author,
            commit_message=commit_message,
        )

        self.db.execute(
            """INSERT INTO prompt_versions
               (id, prompt_id, version, content, model, variables, config,
                author, commit_message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pv.id,
                pv.prompt_id,
                pv.version,
                pv.content,
                pv.model,
                json.dumps(pv.variables),
                json.dumps(pv.config),
                pv.author,
                pv.commit_message,
                pv.created_at,
            ),
        )
        return pv.to_dict()

    def get_version(self, prompt_id: str, version: int) -> dict | None:
        """Get a specific version of a prompt."""
        pid = self._resolve_prompt_id(prompt_id)
        if not pid:
            return None

        row = self.db.fetch_one(
            "SELECT * FROM prompt_versions WHERE prompt_id=? AND version=?",
            (pid, version),
        )
        return self._row_to_version(row) if row else None

    def list_versions(self, prompt_id: str) -> list[dict]:
        """List all versions of a prompt, newest first."""
        pid = self._resolve_prompt_id(prompt_id)
        if not pid:
            return []

        rows = self.db.fetch_all(
            "SELECT * FROM prompt_versions WHERE prompt_id=? ORDER BY version DESC",
            (pid,),
        )
        return [self._row_to_version(r) for r in rows]

    def diff_versions(self, prompt_id: str, v1: int, v2: int) -> dict:
        """Get a unified diff between two versions."""
        ver1 = self.get_version(prompt_id, v1)
        ver2 = self.get_version(prompt_id, v2)

        if not ver1 or not ver2:
            raise ValueError(f"One or both versions not found: v{v1}, v{v2}")

        diff_lines = list(
            difflib.unified_diff(
                ver1["content"].splitlines(keepends=True),
                ver2["content"].splitlines(keepends=True),
                fromfile=f"v{v1}",
                tofile=f"v{v2}",
                lineterm="",
            )
        )

        return {
            "prompt_id": self._resolve_prompt_id(prompt_id),
            "v1": v1,
            "v2": v2,
            "diff": "\n".join(diff_lines),
            "v1_content": ver1["content"],
            "v2_content": ver2["content"],
            "v1_model": ver1["model"],
            "v2_model": ver2["model"],
        }

    # ── Deploy ───────────────────────────────────────────────────

    def deploy(
        self,
        prompt_id: str,
        *,
        version: int,
        environment: str = "production",
        deployed_by: str = "",
    ) -> dict:
        """Deploy a specific version to an environment."""
        pid = self._resolve_prompt_id(prompt_id)
        if not pid:
            raise ValueError(f"Prompt not found: {prompt_id}")

        ver = self.get_version(pid, version)
        if not ver:
            raise ValueError(f"Version {version} not found for prompt {pid}")

        dep_id = str(uuid.uuid4())[:12]
        dep = PromptDeployment(
            id=dep_id,
            prompt_id=pid,
            version_id=ver["id"],
            version=version,
            environment=environment,
            deployed_by=deployed_by,
        )

        # Upsert: replace existing deployment for same prompt+env
        try:
            self.db.execute(
                "DELETE FROM prompt_deployments WHERE prompt_id=? AND environment=?",
                (pid, environment),
            )
        except Exception:
            pass

        self.db.execute(
            """INSERT INTO prompt_deployments
               (id, prompt_id, version_id, version, environment, deployed_at, deployed_by)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                dep.id,
                dep.prompt_id,
                dep.version_id,
                dep.version,
                dep.environment,
                dep.deployed_at,
                dep.deployed_by,
            ),
        )

        logger.info("Deployed prompt %s V%d → %s", pid, version, environment)
        return dep.to_dict()

    def list_deployments(self, prompt_id: str) -> list[dict]:
        """List all deployments of a prompt."""
        pid = self._resolve_prompt_id(prompt_id)
        if not pid:
            return []

        rows = self.db.fetch_all(
            """SELECT * FROM prompt_deployments
               WHERE prompt_id=? ORDER BY deployed_at DESC""",
            (pid,),
        )
        return [
            PromptDeployment(
                id=r["id"],
                prompt_id=r["prompt_id"],
                version_id=r["version_id"],
                version=r["version"],
                environment=r["environment"],
                deployed_at=r["deployed_at"],
                deployed_by=r.get("deployed_by", ""),
            ).to_dict()
            for r in rows
        ]

    # ── Resolve (SDK usage) ──────────────────────────────────────

    def resolve(
        self,
        prompt_id: str,
        *,
        environment: str = "production",
        variables: dict | None = None,
        version: int | None = None,
    ) -> dict:
        """Resolve a prompt for usage — returns filled content.

        If version is specified, returns that version directly.
        Otherwise returns the deployed version for the environment.
        If no deployment exists, returns the latest version.
        """
        pid = self._resolve_prompt_id(prompt_id)
        if not pid:
            raise ValueError(f"Prompt not found: {prompt_id}")

        if version is not None:
            ver = self.get_version(pid, version)
            if not ver:
                raise ValueError(f"Version {version} not found")
        else:
            # Check deployment
            dep = self.db.fetch_one(
                """SELECT version FROM prompt_deployments
                   WHERE prompt_id=? AND environment=?""",
                (pid, environment),
            )
            if dep:
                ver = self.get_version(pid, dep["version"])
            else:
                # Fall back to latest
                prompt = self._get_prompt_row(pid)
                ver = self.get_version(pid, prompt["latest_version"])

        if not ver:
            raise ValueError(f"No version found for prompt {pid}")

        content = ver["content"]
        if variables:
            for key, value in variables.items():
                content = content.replace("{{" + key + "}}", str(value))

        return {
            "prompt_id": pid,
            "version": ver["version"],
            "version_id": ver["id"],
            "environment": environment,
            "content": content,
            "model": ver["model"],
            "config": ver["config"],
            "variables": ver["variables"],
            "variables_filled": variables or {},
        }

    # ── Read ─────────────────────────────────────────────────────

    def get_prompt(self, prompt_id: str) -> dict | None:
        """Get a prompt with its latest version and deployments."""
        pid = self._resolve_prompt_id(prompt_id)
        if not pid:
            return None

        row = self._get_prompt_row(pid)
        if not row:
            return None

        result = self._row_to_prompt(row)
        latest = self.get_version(pid, row["latest_version"])
        if latest:
            result["active_version"] = latest

        deployments = self.list_deployments(pid)
        result["deployments"] = deployments

        return result

    def list_prompts(
        self,
        *,
        project: str | None = None,
        tag: str | None = None,
        org_id: str = "default",
    ) -> list[dict]:
        """List all prompts, optionally filtered."""
        sql = "SELECT * FROM prompts WHERE org_id=?"
        params: list = [org_id]

        if project:
            sql += " AND project=?"
            params.append(project)

        sql += " ORDER BY updated_at DESC"
        rows = self.db.fetch_all(sql, params)

        results = []
        for row in rows:
            p = self._row_to_prompt(row)
            if tag and tag not in p.get("tags", []):
                continue

            # Attach latest version content preview
            latest = self.get_version(p["id"], row["latest_version"])
            if latest:
                p["active_version"] = latest

            # Attach deployment info
            deps = self.list_deployments(p["id"])
            p["deployments"] = deps

            results.append(p)

        return results

    def delete_prompt(self, prompt_id: str) -> bool:
        """Delete a prompt and all its versions/deployments."""
        pid = self._resolve_prompt_id(prompt_id)
        if not pid:
            return False

        self.db.execute("DELETE FROM prompt_deployments WHERE prompt_id=?", (pid,))
        self.db.execute("DELETE FROM prompt_versions WHERE prompt_id=?", (pid,))
        self.db.execute("DELETE FROM prompts WHERE id=?", (pid,))

        logger.info("Deleted prompt %s and all versions", pid)
        return True

    # ── Cost analytics ───────────────────────────────────────────

    def get_version_cost_stats(self, prompt_id: str, version: int) -> dict:
        """Get cost stats for traces tagged with this prompt version.

        Requires traces to have metadata.prompt_id and metadata.prompt_version.
        """
        pid = self._resolve_prompt_id(prompt_id)
        if not pid:
            return {}

        try:
            rows = self.db.fetch_all(
                """SELECT COUNT(*) as call_count,
                          COALESCE(SUM(cost), 0) as total_cost,
                          COALESCE(AVG(cost), 0) as avg_cost,
                          COALESCE(AVG(latency_ms), 0) as avg_latency,
                          COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                          COALESCE(SUM(output_tokens), 0) as total_output_tokens
                   FROM trace_events
                   WHERE metadata LIKE ?""",
                (f'%"prompt_id": "{pid}"%"prompt_version": {version}%',),
            )
            if rows and rows[0]:
                r = rows[0]
                return {
                    "prompt_id": pid,
                    "version": version,
                    "call_count": r["call_count"],
                    "total_cost": round(r["total_cost"], 6),
                    "avg_cost": round(r["avg_cost"], 6),
                    "avg_latency_ms": round(r["avg_latency"], 1),
                    "total_input_tokens": r["total_input_tokens"],
                    "total_output_tokens": r["total_output_tokens"],
                }
        except Exception as e:
            logger.debug("Cost stats query failed: %s", e)

        return {
            "prompt_id": pid,
            "version": version,
            "call_count": 0,
            "total_cost": 0,
            "avg_cost": 0,
            "avg_latency_ms": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }

    def compare_version_costs(self, prompt_id: str, v1: int, v2: int) -> dict:
        """Compare cost stats between two versions."""
        stats1 = self.get_version_cost_stats(prompt_id, v1)
        stats2 = self.get_version_cost_stats(prompt_id, v2)

        cost_delta = stats2.get("avg_cost", 0) - stats1.get("avg_cost", 0)
        latency_delta = stats2.get("avg_latency_ms", 0) - stats1.get(
            "avg_latency_ms", 0
        )

        return {
            "v1": stats1,
            "v2": stats2,
            "cost_delta": round(cost_delta, 6),
            "latency_delta": round(latency_delta, 1),
            "cost_change_pct": (
                round(cost_delta / stats1["avg_cost"] * 100, 1)
                if stats1.get("avg_cost", 0) > 0
                else 0
            ),
        }

    # ── Summary ──────────────────────────────────────────────────

    def get_summary(self) -> dict:
        """Get overall prompt management stats."""
        prompts = self.db.fetch_one("SELECT COUNT(*) as count FROM prompts")
        versions = self.db.fetch_one("SELECT COUNT(*) as count FROM prompt_versions")
        deployments = self.db.fetch_one(
            "SELECT COUNT(*) as count FROM prompt_deployments"
        )

        return {
            "total_prompts": prompts["count"] if prompts else 0,
            "total_versions": versions["count"] if versions else 0,
            "active_deployments": deployments["count"] if deployments else 0,
        }

    # ── Internal helpers ─────────────────────────────────────────

    def _resolve_prompt_id(self, prompt_id: str) -> str | None:
        """Resolve a prompt_id (could be an ID or a name)."""
        row = self._get_prompt_row(prompt_id)
        if row:
            return row["id"]
        row = self._get_prompt_by_name(prompt_id)
        if row:
            return row["id"]
        return None

    def _get_prompt_row(self, prompt_id: str):
        return self.db.fetch_one("SELECT * FROM prompts WHERE id=?", (prompt_id,))

    def _get_prompt_by_name(self, name: str):
        return self.db.fetch_one("SELECT * FROM prompts WHERE name=?", (name,))

    def _row_to_prompt(self, row) -> dict:
        tags = row.get("tags", "[]")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []

        return {
            "id": row["id"],
            "name": row["name"],
            "project": row["project"],
            "description": row.get("description", ""),
            "tags": tags,
            "latest_version": row["latest_version"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "org_id": row.get("org_id", "default"),
        }

    def _row_to_version(self, row) -> dict:
        variables = row.get("variables", "[]")
        if isinstance(variables, str):
            try:
                variables = json.loads(variables)
            except (json.JSONDecodeError, TypeError):
                variables = []

        config = row.get("config", "{}")
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except (json.JSONDecodeError, TypeError):
                config = {}

        return {
            "id": row["id"],
            "prompt_id": row["prompt_id"],
            "version": row["version"],
            "content": row["content"],
            "model": row.get("model", ""),
            "variables": variables,
            "config": config,
            "author": row.get("author", ""),
            "commit_message": row.get("commit_message", ""),
            "created_at": row["created_at"],
        }


# ── Singleton ────────────────────────────────────────────────────────────────

_service: PromptService | None = None


def get_prompt_service(db=None) -> PromptService:
    """Get or create the PromptService singleton."""
    global _service
    if _service is None:
        _service = PromptService(db=db)
    return _service


def reset_prompt_service() -> None:
    """Reset the singleton. Used in tests."""
    global _service
    _service = None
