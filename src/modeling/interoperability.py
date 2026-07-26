"""Cross-parser and optional official-XSD validation for generated SCL artifacts."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from src.modeling.scl_importer import SclModelImporter
from src.modeling.standards import default_standard
from src.proto.iec61850.plugins.scl.service.container import SclServiceContainer
import src.proto.iec61850.plugins.scl.validator.builtin_rules  # noqa: F401


def validate_interoperability(xml: str, *, filename: str) -> dict[str, Any]:
    """Run independent model adapters and report XSD availability without overstating compliance."""

    issues: list[dict[str, str]] = []
    engines: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml)
        engines.append({"engine": "python-elementtree", "passed": root.tag.rsplit("}", 1)[-1] == "SCL"})
    except ET.ParseError as exc:
        engines.append({"engine": "python-elementtree", "passed": False})
        issues.append({"level": "ERROR", "code": "INTEROP_XML_PARSE", "message": str(exc)})

    try:
        imported = SclModelImporter().parse(xml.encode("utf-8"), filename=filename)
        engines.append(
            {
                "engine": "modeling-import-adapter",
                "passed": True,
                "summary": imported.summary,
            }
        )
    except ValueError as exc:
        engines.append({"engine": "modeling-import-adapter", "passed": False})
        issues.append({"level": "ERROR", "code": "INTEROP_IMPORT_ADAPTER", "message": str(exc)})

    try:
        container = SclServiceContainer()
        document = container.parse_string(xml)
        validation = container.validate(document)
        parser_issues = []
        for issue in validation.issues:
            level = "ERROR" if issue.severity.value == "error" else "WARNING"
            item = {"level": level, "code": f"SCL_{issue.rule_id.upper()}", "message": issue.message}
            parser_issues.append(item)
            issues.append(item)
        engines.append(
            {
                "engine": "runtime-scl-parser",
                "passed": not any(item["level"] == "ERROR" for item in parser_issues),
                "issue_count": len(parser_issues),
            }
        )
    except Exception as exc:
        engines.append({"engine": "runtime-scl-parser", "passed": False})
        issues.append({"level": "ERROR", "code": "INTEROP_RUNTIME_PARSER", "message": str(exc)})

    xsd = _validate_optional_xsd(xml)
    issues.extend(xsd.pop("issues"))
    return {
        "passed": not any(issue["level"] == "ERROR" for issue in issues),
        "engines": engines,
        "xsd": xsd,
        "issues": issues,
    }


def _validate_optional_xsd(xml: str) -> dict[str, Any]:
    schema = default_standard().get("schema") or {}
    expected = str(schema.get("expectedPath") or "")
    path, source = _resolve_xsd_path(schema)
    if not expected or not path.is_file():
        return {
            "status": "UNAVAILABLE",
            "path": str(path),
            "source": source,
            "message": "Official project-approved SCL XSD is not installed; no XSD compliance claim was made.",
            "issues": [
                {
                    "level": "WARNING",
                    "code": "XSD_VALIDATION_UNAVAILABLE",
                    "message": (f"未找到经项目批准的 SCL XSD：{path}；当前结果不代表通过官方 Schema 校验"),
                }
            ],
        }
    if importlib.util.find_spec("lxml") is None:
        return {
            "status": "ENGINE_UNAVAILABLE",
            "path": str(path),
            "source": source,
            "message": "The XSD exists but the lxml validation engine is not installed.",
            "issues": [
                {
                    "level": "ERROR",
                    "code": "XSD_ENGINE_UNAVAILABLE",
                    "message": "Official XSD validation cannot run because lxml is unavailable.",
                }
            ],
        }

    from lxml import etree

    try:
        validator = etree.XMLSchema(etree.parse(str(path)))
        document = etree.fromstring(xml.encode("utf-8"))
        passed = validator.validate(document)
    except (etree.XMLSyntaxError, etree.XMLSchemaParseError) as exc:
        return {
            "status": "FAILED",
            "path": str(path),
            "source": source,
            "message": str(exc),
            "issues": [{"level": "ERROR", "code": "XSD_LOAD_FAILED", "message": str(exc)}],
        }
    xsd_issues = [
        {"level": "ERROR", "code": "XSD_VALIDATION_ERROR", "message": str(entry)} for entry in validator.error_log
    ]
    return {
        "status": "PASSED" if passed else "FAILED",
        "path": str(path),
        "source": source,
        "message": "Official XSD validation passed." if passed else "Official XSD validation failed.",
        "issues": xsd_issues,
    }


def xsd_required_for_publish() -> bool:
    """Return whether publishing must be blocked unless the approved XSD passes."""

    schema = default_standard().get("schema") or {}
    environment = str(schema.get("requiredEnvironment") or "EMS_REQUIRE_SCL_XSD")
    configured = os.getenv(environment)
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return bool(schema.get("requiredForPublish"))


def _resolve_xsd_path(schema: dict[str, Any]) -> tuple[Path, str]:
    environment = str(schema.get("pathEnvironment") or "EMS_SCL_XSD_PATH")
    override = os.getenv(environment, "").strip()
    if override:
        return Path(override).expanduser().resolve(), f"environment:{environment}"
    expected = str(schema.get("expectedPath") or "")
    path = Path(expected)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return path.resolve(), "standard-package"
