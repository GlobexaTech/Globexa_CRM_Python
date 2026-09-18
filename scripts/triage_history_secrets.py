"""Verify only the individually reviewed, immutable historical scan findings.

This is not a Gitleaks allowlist: the scanner still reports every finding and
new/changed/missing fingerprints fail the release gate. Never emit secret data.
"""
import argparse
from collections import Counter
import json
from pathlib import Path


def reviewed_findings() -> list[dict]:
    findings = []
    for commit, file, rule, lines, classification, span in (
        ("71fbc0cff4eafc935914f374951be3ad135cdaa6", ".github/workflows/checkpoint-2.yml",
         "generic-api-key", (78, 170, 213, 222), "synthetic_test_literal", 0),
        ("71fbc0cff4eafc935914f374951be3ad135cdaa6", "tests/test_security.py",
         "generic-api-key", (270,), "synthetic_test_literal", 0),
        ("c2127ab53da5fd75158a8f66bdb296ba43acf1e2", "PHASE1_ACCESS.md",
         "curl-auth-header", (173, 179, 193, 219, 223), "documentation_placeholder", 1),
        ("c2127ab53da5fd75158a8f66bdb296ba43acf1e2", "PHASE5_ACCESS.md",
         "curl-auth-header", (87, 92, 97, 119, 127, 135, 143, 151, 159, 181, 189, 197),
         "documentation_placeholder", 1),
    ):
        for line in lines:
            findings.append({"Commit": commit, "File": file, "RuleID": rule,
                             "StartLine": line, "EndLine": line + span,
                             "Fingerprint": f"{commit}:{file}:{rule}:{line}",
                             "classification": classification})
    return findings


def triage(report: list[dict]) -> dict:
    if not isinstance(report, list):
        raise ValueError("History scan must be a JSON array")
    reviewed = {finding["Fingerprint"]: finding for finding in reviewed_findings()}
    accepted = []
    unresolved = 0
    seen = set()
    for finding in report:
        if not isinstance(finding, dict):
            unresolved += 1
            continue
        fingerprint = finding.get("Fingerprint")
        expected = reviewed.get(fingerprint) if isinstance(fingerprint, str) else None
        if (not expected or fingerprint in seen
                or any(finding.get(key) != value for key, value in expected.items() if key != "classification")
                or finding.get("Secret") != "REDACTED"
                or "REDACTED" not in str(finding.get("Match", ""))):
            unresolved += 1
            continue
        seen.add(fingerprint)
        accepted.append(expected)
    missing = sorted(set(reviewed) - seen)
    classifications = dict(sorted(Counter(row["classification"] for row in accepted).items()))
    return {
        "schema_version": 1,
        "scanner": "gitleaks 8.30.1, full Git history, --redact",
        "total": len(report), "reviewed": len(accepted), "unresolved": unresolved,
        "missing_reviewed_fingerprints": missing,
        "classification_counts": classifications,
        "findings": sorted(accepted, key=lambda row: row["Fingerprint"]),
        "passed": unresolved == 0 and not missing and len(accepted) == 22,
        "rotation_note": (
            "Historical static CI test key: ROTATION REQUIRED if ever reused outside isolated CI. "
            "Current CI/runtime keys are generated. Reviewed findings contain documentation "
            "placeholders and synthetic test literals; no production credential was identified."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = triage(json.loads(args.report.read_text(encoding="utf-8-sig")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"History triage: {result['reviewed']} reviewed; {result['unresolved']} unresolved; "
          f"{len(result['missing_reviewed_fingerprints'])} expected fingerprints missing.")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
