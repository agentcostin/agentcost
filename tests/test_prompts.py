"""Tests for the AgentCost Prompt Management module."""

import json
import time

import pytest

from agentcost.data.sqlite_adapter import SQLiteAdapter
from agentcost.data.connection import set_db, reset_db
from agentcost.prompts import PromptService, get_prompt_service, reset_prompt_service


@pytest.fixture
def svc():
    return get_prompt_service()


# ── Create ───────────────────────────────────────────────────────────────────


class TestCreatePrompt:
    def test_create_basic(self, svc):
        result = svc.create_prompt("test-prompt", content="Hello {{name}}")
        assert result["name"] == "test-prompt"
        assert result["latest_version"] == 1
        assert result["active_version"]["version"] == 1
        assert result["active_version"]["content"] == "Hello {{name}}"

    def test_create_with_all_fields(self, svc):
        result = svc.create_prompt(
            "full-prompt",
            project="my-project",
            content="System: you are {{role}}",
            description="A test prompt",
            tags=["support", "v1"],
            model="gpt-4.1",
            config={"temperature": 0.7, "max_tokens": 500},
            author="rajneesh",
            commit_message="First version",
        )
        assert result["project"] == "my-project"
        assert result["description"] == "A test prompt"
        assert result["tags"] == ["support", "v1"]
        v = result["active_version"]
        assert v["model"] == "gpt-4.1"
        assert v["config"]["temperature"] == 0.7
        assert v["author"] == "rajneesh"
        assert v["commit_message"] == "First version"

    def test_variable_extraction(self, svc):
        result = svc.create_prompt(
            "vars-test",
            content="Hello {{name}}, welcome to {{product}}. Your role is {{role}}.",
        )
        v = result["active_version"]
        assert sorted(v["variables"]) == ["name", "product", "role"]

    def test_no_variables(self, svc):
        result = svc.create_prompt(
            "no-vars", content="A plain prompt with no placeholders."
        )
        assert result["active_version"]["variables"] == []

    def test_duplicate_name_raises(self, svc):
        svc.create_prompt("dup-test", content="V1")
        with pytest.raises(Exception):
            svc.create_prompt("dup-test", content="V2")


# ── Versions ─────────────────────────────────────────────────────────────────


class TestVersions:
    def test_create_version(self, svc):
        p = svc.create_prompt("ver-test", content="V1 content")
        v2 = svc.create_version(p["id"], content="V2 content", commit_message="Update")
        assert v2["version"] == 2
        assert v2["content"] == "V2 content"
        assert v2["commit_message"] == "Update"

    def test_create_version_by_name(self, svc):
        svc.create_prompt("named-prompt", content="V1")
        v2 = svc.create_version("named-prompt", content="V2")
        assert v2["version"] == 2

    def test_version_increments(self, svc):
        p = svc.create_prompt("inc-test", content="V1")
        svc.create_version(p["id"], content="V2")
        v3 = svc.create_version(p["id"], content="V3")
        assert v3["version"] == 3

    def test_get_specific_version(self, svc):
        p = svc.create_prompt("get-ver", content="First")
        svc.create_version(p["id"], content="Second")
        svc.create_version(p["id"], content="Third")

        v1 = svc.get_version(p["id"], 1)
        v3 = svc.get_version(p["id"], 3)
        assert v1["content"] == "First"
        assert v3["content"] == "Third"

    def test_list_versions_newest_first(self, svc):
        p = svc.create_prompt("list-ver", content="V1")
        svc.create_version(p["id"], content="V2")
        svc.create_version(p["id"], content="V3")

        versions = svc.list_versions(p["id"])
        assert len(versions) == 3
        assert versions[0]["version"] == 3
        assert versions[2]["version"] == 1

    def test_version_not_found(self, svc):
        p = svc.create_prompt("no-ver", content="V1")
        assert svc.get_version(p["id"], 99) is None

    def test_version_for_nonexistent_prompt(self, svc):
        with pytest.raises(ValueError):
            svc.create_version("nonexistent", content="V1")


# ── Diff ─────────────────────────────────────────────────────────────────────


class TestDiff:
    def test_diff_versions(self, svc):
        p = svc.create_prompt("diff-test", content="Line 1\nLine 2\nLine 3")
        svc.create_version(p["id"], content="Line 1\nModified Line 2\nLine 3\nLine 4")

        diff = svc.diff_versions(p["id"], 1, 2)
        assert "diff" in diff
        assert "-Line 2" in diff["diff"] or "+Modified Line 2" in diff["diff"]
        assert diff["v1"] == 1
        assert diff["v2"] == 2

    def test_diff_nonexistent_version(self, svc):
        p = svc.create_prompt("diff-err", content="V1")
        with pytest.raises(ValueError):
            svc.diff_versions(p["id"], 1, 99)


# ── Deploy ───────────────────────────────────────────────────────────────────


class TestDeploy:
    def test_deploy_to_production(self, svc):
        p = svc.create_prompt("deploy-test", content="V1")
        svc.create_version(p["id"], content="V2 better")

        dep = svc.deploy(p["id"], version=2, environment="production")
        assert dep["version"] == 2
        assert dep["environment"] == "production"

    def test_deploy_to_staging(self, svc):
        p = svc.create_prompt("stage-test", content="V1")
        dep = svc.deploy(p["id"], version=1, environment="staging")
        assert dep["environment"] == "staging"

    def test_deploy_replaces_existing(self, svc):
        p = svc.create_prompt("replace-test", content="V1")
        svc.create_version(p["id"], content="V2")
        svc.create_version(p["id"], content="V3")

        svc.deploy(p["id"], version=2, environment="production")
        svc.deploy(p["id"], version=3, environment="production")

        deps = svc.list_deployments(p["id"])
        prod_deps = [d for d in deps if d["environment"] == "production"]
        assert len(prod_deps) == 1
        assert prod_deps[0]["version"] == 3

    def test_deploy_different_envs(self, svc):
        p = svc.create_prompt("multi-env", content="V1")
        svc.create_version(p["id"], content="V2")

        svc.deploy(p["id"], version=1, environment="staging")
        svc.deploy(p["id"], version=2, environment="production")

        deps = svc.list_deployments(p["id"])
        assert len(deps) == 2

    def test_deploy_nonexistent_version(self, svc):
        p = svc.create_prompt("dep-err", content="V1")
        with pytest.raises(ValueError):
            svc.deploy(p["id"], version=99, environment="production")

    def test_list_deployments(self, svc):
        p = svc.create_prompt("dep-list", content="V1")
        svc.create_version(p["id"], content="V2")
        svc.deploy(p["id"], version=1, environment="staging")
        svc.deploy(p["id"], version=2, environment="production")

        deps = svc.list_deployments(p["id"])
        assert len(deps) == 2
        envs = {d["environment"] for d in deps}
        assert envs == {"staging", "production"}


# ── Resolve ──────────────────────────────────────────────────────────────────


class TestResolve:
    def test_resolve_deployed(self, svc):
        p = svc.create_prompt("resolve-test", content="V1: Hello {{name}}")
        svc.create_version(p["id"], content="V2: Hi {{name}}, welcome!")
        svc.deploy(p["id"], version=2, environment="production")

        result = svc.resolve(
            p["id"], environment="production", variables={"name": "Rajneesh"}
        )
        assert result["content"] == "V2: Hi Rajneesh, welcome!"
        assert result["version"] == 2

    def test_resolve_falls_back_to_latest(self, svc):
        p = svc.create_prompt("fallback-test", content="Latest: {{x}}")
        # No deployment — should resolve to latest
        result = svc.resolve(p["id"], variables={"x": "42"})
        assert result["content"] == "Latest: 42"
        assert result["version"] == 1

    def test_resolve_specific_version(self, svc):
        p = svc.create_prompt("specific-ver", content="V1")
        svc.create_version(p["id"], content="V2")
        svc.create_version(p["id"], content="V3")

        result = svc.resolve(p["id"], version=2)
        assert result["content"] == "V2"
        assert result["version"] == 2

    def test_resolve_multiple_variables(self, svc):
        p = svc.create_prompt(
            "multi-var",
            content="Welcome {{user}} to {{product}}. Your plan is {{plan}}.",
        )
        result = svc.resolve(
            p["id"],
            variables={"user": "John", "product": "AgentCost", "plan": "Enterprise"},
        )
        assert "John" in result["content"]
        assert "AgentCost" in result["content"]
        assert "Enterprise" in result["content"]

    def test_resolve_by_name(self, svc):
        svc.create_prompt("named-resolve", content="Hello {{who}}")
        result = svc.resolve("named-resolve", variables={"who": "World"})
        assert result["content"] == "Hello World"

    def test_resolve_nonexistent_raises(self, svc):
        with pytest.raises(ValueError):
            svc.resolve("nonexistent")


# ── Read / List / Delete ─────────────────────────────────────────────────────


class TestReadListDelete:
    def test_get_prompt_with_details(self, svc):
        p = svc.create_prompt("detail-test", content="Hello", description="Test")
        svc.create_version(p["id"], content="Updated")
        svc.deploy(p["id"], version=2, environment="production")

        result = svc.get_prompt(p["id"])
        assert result["name"] == "detail-test"
        assert result["latest_version"] == 2
        assert result["active_version"]["version"] == 2
        assert len(result["deployments"]) == 1

    def test_get_prompt_by_name(self, svc):
        svc.create_prompt("by-name", content="Test")
        result = svc.get_prompt("by-name")
        assert result is not None
        assert result["name"] == "by-name"

    def test_get_nonexistent(self, svc):
        assert svc.get_prompt("nonexistent") is None

    def test_list_all_prompts(self, svc):
        svc.create_prompt("p1", content="First")
        svc.create_prompt("p2", content="Second")
        svc.create_prompt("p3", content="Third")

        prompts = svc.list_prompts()
        assert len(prompts) == 3

    def test_list_by_project(self, svc):
        svc.create_prompt("p1", project="alpha", content="A")
        svc.create_prompt("p2", project="beta", content="B")
        svc.create_prompt("p3", project="alpha", content="C")

        alpha = svc.list_prompts(project="alpha")
        assert len(alpha) == 2

        beta = svc.list_prompts(project="beta")
        assert len(beta) == 1

    def test_list_by_tag(self, svc):
        svc.create_prompt("t1", tags=["support", "v1"], content="A")
        svc.create_prompt("t2", tags=["sales"], content="B")
        svc.create_prompt("t3", tags=["support", "v2"], content="C")

        support = svc.list_prompts(tag="support")
        assert len(support) == 2

    def test_delete_prompt(self, svc):
        p = svc.create_prompt("del-test", content="To be deleted")
        svc.create_version(p["id"], content="V2")
        svc.deploy(p["id"], version=1, environment="staging")

        assert svc.delete_prompt(p["id"])
        assert svc.get_prompt(p["id"]) is None
        assert svc.list_versions(p["id"]) == []
        assert svc.list_deployments(p["id"]) == []

    def test_delete_nonexistent(self, svc):
        assert not svc.delete_prompt("nonexistent")


# ── Cost Analytics ───────────────────────────────────────────────────────────


class TestCostAnalytics:
    def test_version_cost_stats_no_traces(self, svc):
        p = svc.create_prompt("cost-test", content="Hello")
        stats = svc.get_version_cost_stats(p["id"], 1)
        assert stats["call_count"] == 0
        assert stats["total_cost"] == 0

    def test_compare_version_costs_no_traces(self, svc):
        p = svc.create_prompt("compare-test", content="V1")
        svc.create_version(p["id"], content="V2")
        comparison = svc.compare_version_costs(p["id"], 1, 2)
        assert comparison["cost_delta"] == 0
        assert "v1" in comparison
        assert "v2" in comparison


# ── Summary ──────────────────────────────────────────────────────────────────


class TestSummary:
    def test_summary(self, svc):
        svc.create_prompt("s1", content="A")
        svc.create_prompt("s2", content="B")
        p = svc.create_prompt("s3", content="C")
        svc.create_version(p["id"], content="C2")
        svc.deploy(p["id"], version=2, environment="production")

        summary = svc.get_summary()
        assert summary["total_prompts"] == 3
        assert summary["total_versions"] == 4  # 3 initial + 1 new
        assert summary["active_deployments"] == 1
