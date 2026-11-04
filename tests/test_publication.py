import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("exporter", ROOT / "scripts/export_evaluations.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def test_redaction_preserves_json_and_synthetic_fields():
    value = (
        '{"workspace":"' + "E:" + '/private/run",'
        '"question":"植物园在哪？","token":"' + "sk-" + "a" * 30 + '"}'
    )
    public, counts = exporter.sanitize_bytes(Path("settings.json"), value.encode())
    assert b"LOCAL_PATH" in public and b"REDACTED_CREDENTIAL" in public
    assert counts == {"local_path": 1, "credential_shape": 1, "network_address": 0}
    assert "植物园在哪？" in public.decode()


def test_export_is_explicit_allowlist():
    for name in [
        "state.sqlite",
        "new.toml",
        "grading/requests.jsonl",
        "arms/new/db.sqlite",
        ".env",
        "monitor_status.py",
        "upstream/private-corpus.json",
    ]:
        assert not exporter.include(Path(name))
    for name in [
        "bank/suite-v1/questions.jsonl",
        "bank/suite-v1/assets/story.wav",
        "grading/vote-0/grades.jsonl",
        "build_bank.py",
    ]:
        assert exporter.include(Path(name))


def test_public_urls_and_svg_namespaces_are_preserved():
    text = "https://github.com/Tidekin http://www.w3.org/2000/svg"
    assert exporter.sanitize(text)[0] == text


def test_private_key_stops_export():
    value = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
    with pytest.raises(ValueError, match="PRIVATE_KEY"):
        exporter.sanitize(value)
