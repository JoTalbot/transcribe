from transcribe_intelligence.job_store import ExecutionJob
from transcribe_intelligence.orchestrator import build_ready_plan, execute_decisions


def job(recording_id, stage, status="queued", artifact_id=None):
    return ExecutionJob(f"{recording_id}:{stage}", recording_id, stage, status, artifact_id=artifact_id)


def test_plan_waits_for_dependencies_and_runs_ready_stage():
    jobs = [job("r", "normalize"), job("r", "ingest", "completed", "a1")]
    decisions = build_ready_plan(jobs, {("r", "ingest")})
    assert [(item.task.stage, item.action) for item in decisions] == [
        ("ingest", "skip"),
        ("normalize", "run"),
    ]


def test_completed_job_is_skipped_even_when_completed_set_is_empty():
    decisions = build_ready_plan([job("r", "ingest", "completed", "a1")], set())
    assert decisions[0].action == "skip"


def test_execute_runs_only_run_decisions():
    decisions = build_ready_plan(
        [job("r", "ingest"), job("r", "normalize")],
        set(),
    )
    seen = []
    execute_decisions(decisions, lambda task: seen.append(task.stage))
    assert seen == ["ingest"]
