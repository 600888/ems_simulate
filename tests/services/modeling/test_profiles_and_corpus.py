from pathlib import Path

import pytest

from scripts.analyze_scl_corpus import analyze
from src.modeling.profiles import profile_lock, resolve_profiles
from src.modeling.standards import default_standard


def test_profile_dependencies_are_resolved_and_version_locked():
    resolved = resolve_profiles(["pcs-bess", "generic-goose-publisher"])
    assert resolved == ["generic-ied-ed2", "generic-reporting", "pcs-bess", "generic-goose-publisher"]
    assert profile_lock(resolved)[0] == {"id": "generic-ied-ed2", "version": "1.0.0"}


def test_standard_package_contains_sample_compatible_basic_types():
    standard = default_standard()
    assert standard["sclVersion"] == "2007"
    assert {"Dbpos", "VisString64", "INT128"} <= set(standard["basicTypes"])
    assert standard["schema"]["bundled"] is False


def test_scl_corpus_baseline_matches_phase_zero_inventory():
    corpus = Path("tmp/testicd").resolve()
    if not corpus.exists():
        pytest.skip("本地黄金样例目录未提供")
    summary = analyze(corpus)["summary"]
    assert summary == {
        "files": 66,
        "valid": 62,
        "damaged": 4,
        "unique_binary_files": 58,
        "duplicate_groups": [3, 3, 2, 2, 2, 2],
    }
