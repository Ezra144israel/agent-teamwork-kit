#!/usr/bin/env python3
"""Compile the local renderer and regenerate all public demonstration assets."""

import hashlib
import json
import platform
from pathlib import Path
import shutil
import subprocess
import tempfile


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            value.update(chunk)
    return value.hexdigest()


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def render(binary: Path, evidence: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    metadata = output / "renderer-metadata.json"
    subprocess.run(
        [
            str(binary),
            str(evidence),
            str(output / "destructive-guardian-16x9.mp4"),
            str(output / "destructive-guardian-9x16.mp4"),
            str(output / "destructive-guardian-poster.png"),
            str(metadata),
        ],
        check=True,
    )
    return json.loads(metadata.read_text(encoding="utf-8"))


def main() -> int:
    demo = Path(__file__).resolve().parent
    repository = demo.parents[1]
    evidence = demo / "evidence/public-evidence.json"
    subprocess.run(["python3", str(demo / "validate_evidence.py"), str(evidence)], check=True)
    assets = repository / "assets/destructive-guardian"
    assets.mkdir(parents=True, exist_ok=True)
    binary_dir = Path(tempfile.mkdtemp(prefix="guard-renderer-"))
    try:
        binary = binary_dir / "render_media"
        subprocess.run(
            [
                "xcrun",
                "clang",
                "-fobjc-arc",
                "-framework",
                "Foundation",
                "-framework",
                "AppKit",
                "-framework",
                "AVFoundation",
                "-framework",
                "CoreGraphics",
                "-framework",
                "CoreMedia",
                "-framework",
                "CoreText",
                "-framework",
                "CoreVideo",
                str(demo / "render_media.m"),
                "-o",
                str(binary),
            ],
            check=True,
        )
        final_metadata = render(binary, evidence, assets)
        with tempfile.TemporaryDirectory(prefix="guard-render-check-") as second_dir:
            second = Path(second_dir)
            second_metadata = render(binary, evidence, second)
            if final_metadata != second_metadata:
                raise SystemExit("renderer semantic metadata changed on the second clean run")
            if any(final_metadata[key]["audio_tracks"] != 0 for key in ("wide", "vertical")):
                raise SystemExit("renderer produced an audio track")
            byte_reproducible = all(
                digest(assets / name) == digest(second / name)
                for name in (
                    "destructive-guardian-16x9.mp4",
                    "destructive-guardian-9x16.mp4",
                    "destructive-guardian-poster.png",
                )
            )
    finally:
        shutil.rmtree(binary_dir, ignore_errors=True)

    captions = """WEBVTT

00:00.000 --> 00:04.000
Verified capture replay. The same harmless command appears in both terminals.

00:04.000 --> 00:09.000
Without the guard, GUARD_INACTIVE_PROOF prints. The missing sentinel fails with shell exit 127.

00:09.000 --> 00:16.000
With the guard, the request moves from the agent to the PreToolUse guard. The guard stops it before the shell.

00:16.000 --> 00:25.000
The exact denial appears. There is no command execution event and no marker output.

00:25.000 --> 00:28.000
Skills are the Instruction Layer. Hooks and guards are the Enforcement Layer.
"""
    write(assets / "destructive-guardian.vtt", captions)
    transcript = """# Destructive Guardian demonstration transcript

0-4 seconds: This is an automated replay from the verified public capture, not a live screen recording. The same harmless command appears in both terminals.

4-9 seconds: The terminal titled "Without the guard" replays the unprotected result. `GUARD_INACTIVE_PROOF` prints. The missing `destructive-guardian-self-test` sentinel returns the shell error and exit 127.

9-16 seconds: The terminal titled "With the guard" shows `Agent -> PreToolUse guard -> Shell`. The guard stops the tool call before the shell.

16-25 seconds: The exact denial is `Destructive Guardian self-test denied before Bash execution.` The capture has zero protected `command_execution` events and no marker output.

25-28 seconds: Skills are the Instruction Layer. Hooks and guards are the Enforcement Layer.

There is no voice and no audio track.
"""
    write(assets / "destructive-guardian-transcript.md", transcript)

    compiler = subprocess.run(["xcrun", "clang", "--version"], text=True, capture_output=True, check=True).stdout.splitlines()[0]
    sdk = subprocess.run(["xcrun", "--show-sdk-path"], text=True, capture_output=True, check=True).stdout.strip()
    evidence_value = json.loads(evidence.read_text(encoding="utf-8"))
    files = {}
    dimensions = {
        "destructive-guardian-16x9.mp4": [final_metadata["wide"]["width"], final_metadata["wide"]["height"]],
        "destructive-guardian-9x16.mp4": [final_metadata["vertical"]["width"], final_metadata["vertical"]["height"]],
        "destructive-guardian-poster.png": [1280, 720],
    }
    for path in sorted(assets.iterdir()):
        if path.name in {"artifact-manifest.json", "renderer-metadata.json"}:
            continue
        entry = {"sha256": digest(path), "bytes": path.stat().st_size}
        if path.name in dimensions:
            entry["dimensions"] = dimensions[path.name]
        if path.suffix == ".mp4":
            key = "wide" if "16x9" in path.name else "vertical"
            entry.update({
                "frame_rate": final_metadata[key]["frame_rate"],
                "duration_seconds": final_metadata[key]["duration_seconds"],
                "audio_tracks": final_metadata[key]["audio_tracks"],
                "video_tracks": final_metadata[key]["video_tracks"],
                "semantic_frame_hash": final_metadata[key]["semantic_frame_hash"],
            })
        files[path.name] = entry
    manifest = {
        "schema": "destructive-guardian-artifacts/v1",
        "source_evidence": {
            "path": str(evidence.relative_to(repository)),
            "sha256": digest(evidence),
            "schema": evidence_value["schema"],
        },
        "renderer": {
            "path": str((demo / "render_media.m").relative_to(repository)),
            "sha256": digest(demo / "render_media.m"),
            "compiler": compiler,
            "sdk": Path(sdk).name,
            "os": platform.mac_ver()[0],
            "codec": "H.264 High Auto Level",
            "frame_rate": 30,
            "duration_seconds": 28,
            "byte_reproducible_on_second_clean_run": byte_reproducible,
            "reproducibility_limit": None if byte_reproducible else "Platform H.264 encoding can change container bytes. Require equal text, timings, dimensions, frame rate, duration, and source evidence identity.",
        },
        "files": files,
    }
    (assets / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (assets / "renderer-metadata.json").unlink(missing_ok=True)
    pages_assets = repository / "docs/assets/destructive-guardian"
    pages_assets.mkdir(parents=True, exist_ok=True)
    for name in files:
        shutil.copyfile(assets / name, pages_assets / name)
    print(json.dumps({"assets": len(files), "byte_reproducible": byte_reproducible}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
