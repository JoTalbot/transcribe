from pathlib import Path

from scripts.colab_exchange_worker import process_one as process_colab_one
from scripts.oracle_local_worker import process_one as process_oracle_one
from transcribe_intelligence.exchange import FileExchange, ResultEnvelope
from transcribe_intelligence.exchange_coordinator import ExchangeCoordinator
from transcribe_intelligence.job_store import ExecutionJob, stable_job_id
from transcribe_intelligence.pipeline_contract import Stage
from transcribe_intelligence.repository import InMemoryRepository, Recording
from transcribe_intelligence.worker_capabilities import COLAB_GPU, ORACLE_LOCAL


class LeaseHarnessRepository(InMemoryRepository):
    """Small transactional lease double for cross-worker orchestration tests."""

    def claim_job(self, job_id: str, worker: str, lease_seconds: int = 900):
        job = self.get_job(job_id)
        if job is None or job.status not in {"queued", "retry"}:
            return None
        claimed = ExecutionJob(
            job.job_id,
            job.recording_id,
            job.stage,
            "running",
            job.attempt + 1,
            job.artifact_id,
            worker,
            None,
            job.updated_at,
            f"lease-{job.attempt + 1}",
            None,
            None,
        )
        return self.update_job(claimed)

    def heartbeat(self, job_id: str, worker: str, lease_id: str, lease_seconds: int = 900):
        job = self.get_job(job_id)
        if job is None or job.status != "running" or job.worker != worker or job.lease_id != lease_id:
            raise RuntimeError("lease heartbeat rejected")
        return job

    def complete(self, job_id: str, worker: str, lease_id: str, artifact_id: str):
        job = self.get_job(job_id)
        if job is None or job.status != "running" or job.worker != worker or job.lease_id != lease_id:
            raise RuntimeError("lease completion rejected")
        return self.update_job(
            ExecutionJob(
                job.job_id,
                job.recording_id,
                job.stage,
                "completed",
                job.attempt,
                artifact_id,
                worker,
                None,
                job.updated_at,
                None,
                None,
                None,
            )
        )

    def fail(self, job_id: str, worker: str, lease_id: str, error: str):
        job = self.get_job(job_id)
        if job is None or job.status != "running" or job.worker != worker or job.lease_id != lease_id:
            raise RuntimeError("lease failure rejected")
        return self.update_job(
            ExecutionJob(
                job.job_id,
                job.recording_id,
                job.stage,
                "failed",
                job.attempt,
                job.artifact_id,
                worker,
                error,
                job.updated_at,
                None,
                None,
                None,
            )
        )

    def release(self, job_id: str, worker: str, lease_id: str, error: str):
        job = self.get_job(job_id)
        if job is None or job.status != "running" or job.worker != worker or job.lease_id != lease_id:
            raise RuntimeError("lease release rejected")
        return self.update_job(
            ExecutionJob(
                job.job_id,
                job.recording_id,
                job.stage,
                "retry",
                job.attempt,
                job.artifact_id,
                None,
                error,
                job.updated_at,
                None,
                None,
                None,
            )
        )


class StubProcessor:
    """CPU-only stand-in for inference while exercising the real worker entrypoint."""

    def process(self, request):
        return ResultEnvelope(
            request.job_id,
            "completed",
            artifact_id=f"{request.recording_id}:{request.stage}:artifact",
        )


def canonical_colab_dry_run_processor(request):
    """Dry-run Colab processor that emits the same canonical IDs as a real worker."""
    return ResultEnvelope(
        request.job_id,
        "completed",
        artifact_id=f"{request.recording_id}:{request.stage}:artifact",
    )


def test_full_nine_stage_pipeline_crosses_oracle_and_colab_workers(tmp_path: Path):
    repository = LeaseHarnessRepository()
    recording_id = "rec-cross-worker"
    repository.put_recording(Recording(recording_id, "/audio/input.wav"))
    for stage in Stage:
        repository.put_job(ExecutionJob(stable_job_id(recording_id, stage.value), recording_id, stage.value))

    exchange = FileExchange(tmp_path / "exchange")
    coordinator = ExchangeCoordinator(
        repository,
        exchange,
        worker_capabilities={ORACLE_LOCAL.worker: ORACLE_LOCAL, COLAB_GPU.worker: COLAB_GPU},
    )
    oracle_audio = StubProcessor()
    oracle_intelligence = StubProcessor()

    expected_workers = {
        Stage.INGEST: ORACLE_LOCAL.worker,
        Stage.NORMALIZE: ORACLE_LOCAL.worker,
        Stage.ASR: COLAB_GPU.worker,
        Stage.DIARIZATION: COLAB_GPU.worker,
        Stage.EMBEDDINGS: COLAB_GPU.worker,
        Stage.TEXT_ANALYSIS: ORACLE_LOCAL.worker,
        Stage.TOPICS: ORACLE_LOCAL.worker,
        Stage.LINKING: ORACLE_LOCAL.worker,
        Stage.GRAPH: ORACLE_LOCAL.worker,
    }
    observed_workers: dict[str, str] = {}
    observed_inputs: dict[str, tuple[str, ...]] = {}

    while True:
        coordinator.cycle(recording_id)
        requests = exchange.list_requests()
        if requests:
            for request_path in requests:
                request = exchange.get_request(request_path.stem)
                observed_workers[request.stage] = request.worker
                observed_inputs[request.stage] = request.input_artifact_ids
                if request.worker == ORACLE_LOCAL.worker:
                    result = process_oracle_one(exchange, request.job_id, oracle_audio, oracle_intelligence)
                else:
                    result = process_colab_one(exchange, request.job_id, canonical_colab_dry_run_processor)
                assert result is not None
            continue
        if all(repository.get_job(stable_job_id(recording_id, stage.value)).status == "completed" for stage in Stage):
            break

    assert observed_workers == {stage.value: worker for stage, worker in expected_workers.items()}
    assert observed_inputs == {
        Stage.INGEST.value: (),
        Stage.NORMALIZE.value: (f"{recording_id}:ingest:artifact",),
        Stage.ASR.value: (f"{recording_id}:normalize:artifact",),
        Stage.DIARIZATION.value: (f"{recording_id}:asr:artifact",),
        Stage.EMBEDDINGS.value: (f"{recording_id}:diarization:artifact",),
        Stage.TEXT_ANALYSIS.value: (f"{recording_id}:asr:artifact",),
        Stage.TOPICS.value: (f"{recording_id}:text_analysis:artifact",),
        Stage.LINKING.value: (
            f"{recording_id}:topics:artifact",
            f"{recording_id}:embeddings:artifact",
        ),
        Stage.GRAPH.value: (f"{recording_id}:linking:artifact",),
    }
    jobs = repository.list_jobs(recording_id)
    assert all(job.status == "completed" for job in jobs)
    assert all(job.artifact_id == f"{recording_id}:{job.stage}:artifact" for job in jobs)
    assert repository.get_recording(recording_id).status == "completed"

    assert not list((exchange.results / "quarantine").glob("*.json"))
