"""
s3-archive — AgentCost Exporter Plugin
"""
import json
from agentcost.plugins import (
    ExporterPlugin, PluginMeta, PluginType,
)


class S3ArchivePlugin(ExporterPlugin):
    meta = PluginMeta(
        name="s3-archive",
        version="0.1.0",
        plugin_type=PluginType.EXPORTER,
        description="Export traces to s3-archive",
    )

    def export(self, traces: list[dict], fmt: str = "json") -> bytes:
        # TODO: Implement your export logic (S3, Snowflake, CSV, etc.)
        if fmt == "csv":
            import csv
            import io
            buf = io.StringIO()
            if traces:
                w = csv.DictWriter(buf, fieldnames=traces[0].keys())
                w.writeheader()
                w.writerows(traces)
            return buf.getvalue().encode()
        return json.dumps(traces, indent=2).encode()

    def supported_formats(self) -> list[str]:
        return ["json", "csv"]
