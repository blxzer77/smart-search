import json
from pathlib import Path
from typing import Any


def artifact_path(evidence_root: str, name: str) -> Path:
    return Path(evidence_root) / name


def write_research_artifact(evidence_root: str, name: str, data: Any) -> None:
    root = Path(evidence_root)
    root.mkdir(parents=True, exist_ok=True)
    path = artifact_path(evidence_root, name)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
