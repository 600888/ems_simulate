"""生成 ICD/CID 黄金样例清单、哈希与结构摘要。"""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

EXTENSIONS = {".icd", ".cid", ".scd", ".iid", ".sed", ".ssd"}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def analyze(root: Path) -> dict:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in EXTENSIONS)
    hashes: Counter[str] = Counter()
    entries = []
    for path in files:
        content = path.read_bytes()
        digest = sha256(content).hexdigest()
        hashes[digest] += 1
        entry = {
            "path": str(path.relative_to(root)).replace("\\", "/"),
            "group": path.relative_to(root).parts[0] if len(path.relative_to(root).parts) > 1 else "root",
            "extension": path.suffix.lower(),
            "bytes": len(content),
            "sha256": digest,
            "status": "valid",
        }
        try:
            document = ET.fromstring(content)
            counts = Counter(local_name(element.tag) for element in document.iter())
            entry["namespace"] = document.tag.split("}", 1)[0].lstrip("{") if "}" in document.tag else ""
            entry["top_level"] = [local_name(child.tag) for child in document]
            entry["counts"] = dict(sorted(counts.items()))
        except ET.ParseError as exc:
            entry["status"] = "damaged"
            entry["error"] = str(exc)
        entries.append(entry)
    valid = sum(entry["status"] == "valid" for entry in entries)
    return {
        "format_version": 1,
        "root": str(root),
        "summary": {
            "files": len(entries),
            "valid": valid,
            "damaged": len(entries) - valid,
            "unique_binary_files": len(hashes),
            "duplicate_groups": sorted((count for count in hashes.values() if count > 1), reverse=True),
        },
        "files": entries,
    }


def main() -> int:
    source = Path(sys.argv[1] if len(sys.argv) > 1 else "tmp/testicd").resolve()
    result = analyze(source)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
