from pathlib import Path

from transcribe_intelligence.artifact_registry import Artifact, ArtifactRegistry


def test_registry_round_trip(tmp_path: Path):
    registry = ArtifactRegistry(tmp_path / "state" / "artifacts.json")
    artifact = Artifact("a1", "asr", "recording-1", model_version="large-v3")

    registry.record(artifact)

    assert registry.load()["a1"] == artifact
