"""A workflow with the run's name, query and update but no logic: the red control for the ported scenarios."""
from temporalio import workflow


@workflow.defn(name="FeatureRun")
class EmptyRun:
    @workflow.run
    async def run(self, start):
        return {}

    @workflow.update(name="answer")
    def answer(self, answer):
        return {}

    @workflow.query(name="status")
    def status(self):
        return {"state": {}, "stop": None, "lines": [], "timeline": [], "queue": None}
