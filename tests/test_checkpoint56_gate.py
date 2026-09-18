"""Release evidence cannot pass on skipped tests, missing reports or findings."""
import json
import pytest
from scripts.checkpoint56_gate import (
    REQUIRED_BACKEND_MODULES, junit_count, unit_count, verify_backend_coverage, verify_scans,
)
from scripts.checkpoint4_public_evidence import reset_public_destination
from scripts.triage_history_secrets import reviewed_findings, triage


def history_findings():
    return [{**{key: value for key, value in finding.items() if key != "classification"},
             "Secret": "REDACTED", "Match": "REDACTED"} for finding in reviewed_findings()]


@pytest.mark.parametrize("field", ["failures", "errors", "skipped"])
def test_gate_rejects_unexecuted_or_failed_mandatory_tests(tmp_path, field):
    report = tmp_path / "tests.xml"
    report.write_text(f'<testsuites><testsuite tests="200" {field}="1" /></testsuites>')
    with pytest.raises(ValueError, match="Mandatory tests"):
        junit_count(report, 135)


def test_gate_rejects_too_few_tests_and_missing_tap_totals(tmp_path):
    report = tmp_path / "tests.xml"
    report.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0" />')
    with pytest.raises(ValueError, match="Too few"):
        junit_count(report, 135)
    tap = tmp_path / "unit.txt"
    tap.write_text("TAP version 13\nok 1 example\n# tests 34\n")
    with pytest.raises(ValueError, match="TAP total"):
        unit_count(tap)


def test_gate_accepts_only_complete_tap_result(tmp_path):
    tap = tmp_path / "unit.txt"
    content = "\n".join(f"# {name} {count}" for name, count in
                        [("tests", 34), ("pass", 34), ("fail", 0), ("cancelled", 0), ("skipped", 0), ("todo", 0)])
    tap.write_text(content)
    assert unit_count(tap) == 34
    tap.write_text(content.replace("# skipped 0", "# skipped 1"))
    with pytest.raises(ValueError, match="unfinished"):
        unit_count(tap)


def test_gate_rejects_secret_history_and_dependency_findings(tmp_path):
    history = history_findings()
    reports = {"gitleaks.json": [], "gitleaks-history.json": history,
               "gitleaks-history-triage.json": triage(history), "bandit.json": {"results": [], "errors": []},
               "pip-audit.json": {"dependencies": [{"name": "example", "vulns": []}]},
               "npm-audit.json": {"metadata": {"vulnerabilities": {"total": 0}}}}
    for name, content in reports.items():
        (tmp_path / name).write_text(json.dumps(content))
    verify_scans(tmp_path)
    (tmp_path / "gitleaks-history.json").write_text('[{"RuleID":"detected-test-finding"}]')
    with pytest.raises(ValueError, match="Secret scan"):
        verify_scans(tmp_path)
    (tmp_path / "gitleaks-history.json").write_text(json.dumps(history))
    (tmp_path / "npm-audit.json").write_text('{"metadata":{"vulnerabilities":{"total":1}}}')
    with pytest.raises(ValueError, match="Node dependency"):
        verify_scans(tmp_path)


def test_history_triage_accepts_only_exact_reviewed_fingerprints():
    history = history_findings()
    result = triage(history)
    assert result["passed"] and result["reviewed"] == 22 and result["unresolved"] == 0
    assert result["classification_counts"] == {"documentation_placeholder": 17, "synthetic_test_literal": 5}
    history[0]["Commit"] = "0" * 40
    result = triage(history)
    assert not result["passed"] and result["unresolved"] == 1


@pytest.mark.parametrize("change", ["missing", "duplicate", "line", "fingerprint", "unredacted"])
def test_history_triage_rejects_incomplete_changed_or_unredacted_reports(change):
    history = history_findings()
    if change == "missing":
        history.pop()
    elif change == "duplicate":
        history.append(history[0].copy())
    elif change == "line":
        history[0]["EndLine"] += 1
    elif change == "fingerprint":
        history[0]["Fingerprint"] += "-unexpected"
    else:
        history[0]["Secret"] = "synthetic-unredacted-finding"
    assert not triage(history)["passed"]


def test_gate_rejects_fabricated_history_triage_counts(tmp_path):
    history = history_findings()
    (tmp_path / "gitleaks.json").write_text("[]")
    (tmp_path / "gitleaks-history.json").write_text(json.dumps(history))
    result = triage(history)
    result["classification_counts"]["documentation_placeholder"] = 22
    (tmp_path / "gitleaks-history-triage.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="inconsistent"):
        verify_scans(tmp_path)


def test_backend_gate_requires_security_rls_and_new_domain_suites(tmp_path):
    report = tmp_path / "backend.xml"
    cases = "".join(f'<testcase classname="{name}" name="verified" />' for name in REQUIRED_BACKEND_MODULES)
    report.write_text(f"<testsuite>{cases}</testsuite>")
    verify_backend_coverage(report)
    report.write_text('<testsuite tests="999"><testcase classname="tests.test_checkpoint3" /></testsuite>')
    with pytest.raises(ValueError, match="Required backend suites"):
        verify_backend_coverage(report)


def test_public_sanitizer_removes_stale_pass_and_unallowlisted_private_artifacts(tmp_path):
    evidence = tmp_path / "evidence"
    destination = evidence / "public-artifact"
    destination.mkdir(parents=True)
    (destination / "CHECKPOINT_5_6_GATE.txt").write_text("stale pass")
    (destination / "private-fixture.json").write_text('{"private":"synthetic"}')
    source = evidence / "fixture.json"
    source.write_text('{"source":"unchanged"}')
    reset_public_destination(destination, evidence)
    assert destination.is_dir() and not list(destination.iterdir())
    assert source.read_text() == '{"source":"unchanged"}'


def test_public_sanitizer_refuses_deleting_evidence_root_or_outside_path(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    for destination in (evidence, tmp_path / "outside", evidence / "private-fixtures"):
        with pytest.raises(RuntimeError, match="remain inside"):
            reset_public_destination(destination, evidence)
    assert evidence.is_dir()
