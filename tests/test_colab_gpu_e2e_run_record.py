from pathlib import Path


RECORD = Path(__file__).parents[1] / "docs" / "COLAB_GPU_E2E_RUN_RECORD_RU.md"

EXPECTED_STAGES = (
    "ingest",
    "normalize",
    "asr",
    "diarization",
    "embeddings",
    "text_analysis",
    "topics",
    "linking",
    "graph",
)


def test_physical_e2e_record_contains_all_stages_and_evidence_sections() -> None:
    text = RECORD.read_text(encoding="utf-8")

    assert "# Transcribe: журнал физического Colab GPU E2E" in text
    assert "## Run metadata" in text
    assert "## Pipeline result" in text
    assert "## Runtime measurements" in text
    assert "## Integrity checks" in text
    assert "## Deterministic repeat" in text
    assert "## Lease interruption / reclaim" in text
    assert "## Evidence files" in text
    assert "## Acceptance" in text

    for stage in EXPECTED_STAGES:
        assert f"| {stage} |" in text


def test_physical_e2e_record_does_not_treat_ci_as_gpu_evidence() -> None:
    text = RECORD.read_text(encoding="utf-8")

    assert "CI, dry-run и ручная проверка кода не являются физическим GPU evidence." in text
    assert "Empty fields are not evidence." in text
