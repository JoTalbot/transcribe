import json
from pathlib import Path

from transcribe_intelligence.artifacts import build_manifest, write_manifest
from transcribe_intelligence.exchange import FileExchange, ResultEnvelope
from transcribe_intelligence.exchange_coordinator import ExchangeCoordinator
from transcribe_intelligence.job_store import ExecutionJob, stable_job_id
from transcribe_intelligence.pipeline_contract import Stage
from transcribe_intelligence.repository import InMemoryRepository, Recording
from transcribe_intelligence.worker_capabilities import COLAB_GPU, ORACLE_LOCAL


STAGES = [
    Stage.INGEST,
    Stage.NORMALIZE,
    Stage.ASR,
    Stage.DIARIZATION,
    Stage.EMBEDDINGS,
    Stage.TEXT_ANALYSIS,
    Stage.TOPICS,
    Stage.LINKING,
    Stage.GRAPH,
]


def _stub_artifact(root: Path, recording_id: str, stage: Stage) -> str:
    artifact_id = f"{recording_id}:{stage.value}:json"
    path = root / recording_id / stage.value / f"{stage.value}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "dry-run", "recording_id": recording_id, "stage": stage.value}, sort_keys=True) + "\n", encoding="utf-8")
    manifest = build_manifest(path, artifact_id=artifact_id, recording_id=recording_id, stage=stage.value, kind="json", producer="dry-run")
    write_manifest(manifest, path.with_name(f"{stage.value}.manifest.json"))
    return artifact_id


def test_canonical_nine_stage_dry_run_reaches_graph(tmp_path: Path):
    recording_id = "dry-run"
    repository = InMemoryRepository()
    repository.put_recording(Recording(recording_id, "/input/dry-run.wav"))
    for stage in STAGES:
        repository.put_job(ExecutionJob(stable_job_id(recording_id, stage.value), recording_id, stage.value))

    exchange = FileExchange(tmp_path / "exchange")
    coordinator = ExchangeCoordinator(
        repository,
        exchange,
        worker_capabilities={COLAB_GPU.worker: COLAB_GPU, ORACLE_LOCAL.worker: ORACLE_LOCAL},
    )

    completed_artifacts: list[str] = []
    completed_jobs: set[str] = set()
    max_cycles = len(STAGES) + 2
    for _ in range(max_cycles):
        dispatches = coordinator.dispatch_ready(recording_id)
        if not dispatches:
            remaining = [job for job in repository.list_jobs(recording_id) if job.status != "completed"]
            if not remaining:
                break
            raise AssertionError(
                "pipeline stalled before graph: " + ", ".join(f"{job.stage}:{job.status}" for job in remaining)
            )
        for dispatch in dispatches:
            request = exchange.get_request(dispatch.job_id)
            job = repository.get_job(dispatch.job_id)
            assert job is not None
            assert request.input_artifact_ids == tuple(
                repository.get_job(f"{recording_id}:{dependency}").artifact_id
                for dependency in __import__("transcribe_intelligence.dependencies", fromlist=["dependencies"]).dependencies(request.stage)
            )
            artifact_id = _stub_artifact(exchange.root / "artifacts", recording_id, Stage(request.stage))
            exchange.put_result(ResultEnvelope(request.job_id, "completed", artifact_id=artifact_id, worker=job.worker, lease_id=job.lease_id))
            completed_artifacts.append(artifact_id)
            completed_jobs.add(request.job_id)
        assert coordinator.apply_results() == len(dispatches)

    assert completed_jobs == {stable_job_id(recording_id, stage.value) for stage in STAGES}
    assert set(completed_artifacts) == {f"{recording_id}:{stage.value}:json" for stage in STAGES}
    jobs = repository.list_jobs(recording_id)
    assert {job.stage for job in jobs if job.status == "completed"} == {stage.value for stage in STAGES}
    assert repository.get_recording(recording_id).status == "completed"
    assert f"{recording_id}:graph:json" in completed_artifacts
