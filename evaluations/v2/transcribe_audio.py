"""Real local ASR over newly synthesized WAV bytes; expected spoken text is not read."""

import hashlib
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(WORKSPACE / ".local/worktrees/memory-recall-probes-20261102"))
from companion_voice_node.providers import FasterWhisperConfig, FasterWhisperProvider

provider = FasterWhisperProvider(FasterWhisperConfig(
    model_dir=WORKSPACE / ".local/next-features-handoff/voice-runtime/models/asr-small",
    device="cpu", compute_type="int8", beam_size=3, cpu_threads=4,
))
output = ROOT / "bank/asr-observations.jsonl"
completed = {json.loads(s)["asset"] for s in output.read_text("utf-8").splitlines()} if output.exists() else set()
for asset in sorted((ROOT / "bank/suite-v1/assets").glob("*.wav")):
    name = asset.relative_to(ROOT / "bank/suite-v1").as_posix()
    if name in completed:
        continue
    data = asset.read_bytes()
    result = provider.transcribe(data)
    with output.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"asset": name, "sha256": hashlib.sha256(data).hexdigest(),
                                 "provider": "native FasterWhisperProvider small CPU int8 beam3",
                                 **asdict(result)}, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(name, len(result.text), flush=True)
