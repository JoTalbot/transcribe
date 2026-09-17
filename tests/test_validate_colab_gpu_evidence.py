from scripts.validate_colab_gpu_evidence import EXPECTED_STAGES, validate


def _payload() -> dict:
    return {
        "schema_version": 2,
        "gpu": {
            "cuda_available": True,
            "gpu": "Test GPU",
            "cuda_version": "12.4",
            "torch_version": "2.0",
            "vram_total_bytes": 1000,
            "peak_vram_allocated_bytes": 500,
        },
        "packages": {
            "faster_whisper": "1",
            "pyannote_audio": "2",
            "speechbrain": "1",
            "torchaudio": "2",
        },
        "runtime": {"worker_metrics": [{"verified": True}]},
        "artifacts": [
            {"stage": stage, "verified": True} for stage in sorted(EXPECTED_STAGES)
        ],
    }


def test_valid_physical_evidence_passes() -> None:
    assert validate(_payload()) == []


def test_cpu_snapshot_is_rejected() -> None:
    payload = _payload()
    payload["gpu"]["cuda_available"] = False

    errors = validate(payload)

    assert any("CUDA is not available" in error for error in errors)


def test_missing_stage_is_rejected() -> None:
    payload = _payload()
    payload["artifacts"] = [
        item for item in payload["artifacts"] if item["stage"] != "diarization"
    ]

    errors = validate(payload)

    assert any("diarization" in error for error in errors)


def test_unverified_metrics_are_rejected() -> None:
    payload = _payload()
    payload["runtime"]["worker_metrics"] = [{"verified": False}]

    errors = validate(payload)

    assert any("verified worker runtime metrics" in error for error in errors)


def test_missing_gpu_package_is_rejected() -> None:
    payload = _payload()
    payload["packages"]["speechbrain"] = None

    errors = validate(payload)

    assert any("packages.speechbrain" in error for error in errors)
