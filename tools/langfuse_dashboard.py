"""Create or update the *Orchestration Health* dashboard in the self-hosted Langfuse.

The dashboard is configuration, so it lives here as data and is applied through
Langfuse's public API instead of being assembled by hand. Running this again gives
the dashboard of that name exactly these widgets and keeps its URL. The widgets
count the rows and scores `telemetry.py` writes, and the suite checks every name
they filter on against that contract.

Not a test and not part of a run: it writes to whatever Langfuse
`telemetry.resolve()` finds.

    uv run --locked python tools/langfuse_dashboard.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from app.foundation import policy as P      # noqa: E402
from app.observability import telemetry as T   # noqa: E402

NAME = "Orchestration Health"
DESCRIPTION = ("How work items end, how often a phase passes at its first judgement, what the "
               "architect decides, how long each role step takes, what the models cost, and "
               "which rows failed or degraded.")
STAGES = [T.stage_name(stage, role) for stage, role in P.STAGE_ROLE.items()]


def _any(column, values):
    return {"column": column, "operator": "any of", "type": "stringOptions", "value": list(values)}


def _widget(name, description, view, dimensions, metrics, filters, chart_type):
    return {"name": name, "description": description, "view": view,
            "dimensions": [{"field": field} for field in dimensions],
            "metrics": [{"measure": measure, "agg": agg} for measure, agg in metrics],
            "filters": filters, "chart_type": chart_type}


# Each widget beside its tile — x, y, width, height on the dashboard's 12-column grid.
TILES = [
    (_widget("Work items", "Work items started.", "observations", [], [("count", "count")],
             [_any("name", [T.RUN_NAME])], "BAR_TIME_SERIES"), (0, 0, 6, 5)),
    # The three outcomes are counted by true and false rather than shown as an average:
    # a number tile rounds, and a first-pass rate of one in two read as 1.
    (_widget("Ended ready for human", "Ended work items: true reached READY_FOR_HUMAN, false was "
             "aborted.", "scores-boolean", ["booleanValue"], [("count", "count")],
             [_any("name", ["final_verify_pass"])], "HORIZONTAL_BAR"), (6, 0, 6, 5)),
    (_widget("Plan passed first time", "Plan phases: true when their first judgement was PASS.",
             "scores-boolean", ["booleanValue"], [("count", "count")], [_any("name", ["plan_first_pass"])],
             "HORIZONTAL_BAR"), (0, 5, 6, 5)),
    (_widget("Build passed first time", "Build phases: true when their first judgement was PASS.",
             "scores-boolean", ["booleanValue"], [("count", "count")], [_any("name", ["build_first_pass"])],
             "HORIZONTAL_BAR"), (6, 5, 6, 5)),
    (_widget("Architect verdicts", "Every architect judgement, by verdict.", "scores-categorical",
             ["stringValue"], [("count", "count")], [_any("name", ["architect_verdict"])],
             "HORIZONTAL_BAR"), (0, 10, 4, 6)),
    (_widget("Role step latency", "p50 and p95 duration of each kind of role step, in milliseconds.",
             "observations", ["name"], [("latency", "p50"), ("latency", "p95")],
             [_any("name", STAGES)], "PIVOT_TABLE"), (4, 10, 8, 6)),
    (_widget("Model cost by model", "Total cost of the agents' model calls, by model.",
             "observations", ["providedModelName"], [("totalCost", "sum")],
             [_any("type", ["GENERATION"])], "HORIZONTAL_BAR"), (0, 16, 4, 6)),
    (_widget("Tokens by model", "Input and output tokens of the agents' model calls, by model.",
             "observations", ["providedModelName"], [("inputTokens", "sum"), ("outputTokens", "sum")],
             [_any("type", ["GENERATION"])], "PIVOT_TABLE"), (4, 16, 4, 6)),
    (_widget("Tool calls by level", "Every tool call the agents made; ERROR is a call that failed.",
             "observations", ["level"], [("count", "count")], [_any("type", ["TOOL"])], "PIE"),
     (8, 16, 4, 6)),
    (_widget("Failed or degraded rows", "This component's rows at WARNING or ERROR, by kind and "
             "level. The Needs Attention view lists them with their error type.", "observations",
             ["name", "level"], [("count", "count")],
             [_any("level", ["WARNING", "ERROR"]), _any("name", T.ROW_NAMES)], "PIVOT_TABLE"),
     (0, 22, 12, 6)),
]
WIDGETS = [widget for widget, _ in TILES]


def apply(client):
    """Create the dashboard, or give the one already named so exactly these widgets. Returns its id."""
    from langfuse.api.unstable.dashboards.types import (CreateDashboardPlacementRequest_Widget,
                                                         DashboardDefinition)
    api = client.api.unstable
    existing = [dashboard for dashboard in api.dashboards.list(limit=100).data
                if dashboard.name == NAME]
    if existing:
        dashboard = existing[0]
        stale = [placement.widget_id for placement in dashboard.definition.widgets
                 if getattr(placement, "type", None) == "widget"]
        # The placements go first, so no tile is left pointing at a deleted widget.
        api.dashboards.update(dashboard.id, description=DESCRIPTION,
                              definition=DashboardDefinition(widgets=[]))
        for widget_id in stale:
            api.dashboard_widgets.delete(widget_id)
    else:
        dashboard = api.dashboards.create(name=NAME, description=DESCRIPTION)
    for widget, (x, y, width, height) in TILES:
        created = api.dashboard_widgets.create(**widget)
        api.dashboards.add_placement(dashboard.id, request=CreateDashboardPlacementRequest_Widget(
            widget_id=created.id, x=x, y=y, width=width, height=height))
    return dashboard.id


def main():
    client = T.resolve()
    if client is None:
        print("no Langfuse keys (secrets/langfuse.env) - nothing to apply", file=sys.stderr)
        return 1
    print("dashboard %r: %d widgets, id %s" % (NAME, len(TILES), apply(client)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
