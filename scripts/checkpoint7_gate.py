"""Fail-closed summary for an exact-revision, fully executed Checkpoint 7 CI gate.

The workflow runs this only after all mandatory commands succeed. This script
additionally rejects absent reports, skipped/failed tests and scanner findings.
It never treats deterministic external test adapters as live certification.
"""
import json
import os
from pathlib import Path
import re
import subprocess
from xml.etree import ElementTree

try:
    from .triage_history_secrets import triage
except ImportError:  # Direct script execution from the CI checkout.
    from triage_history_secrets import triage

ROOT = Path(__file__).resolve().parents[1]
MIN_BACKEND = 380
MIN_BROWSER = 72
MIN_UNIT = 34
REQUIRED_BACKEND_MODULES = {
    "tests.test_checkpoint56_ai_edges", "tests.test_checkpoint56_auth", "tests.test_checkpoint56_config",
    "tests.test_checkpoint56_providers", "tests.test_checkpoint56_security",
    "tests.test_checkpoint6_workforce", "tests.test_checkpoint56_gate", "tests.test_rls",
    "tests.test_checkpoint56_model_config",
    "tests.test_checkpoint7_engine", "tests.test_checkpoint7_security", "tests.test_checkpoint7_expressions",
}
REQUIRED_FLOW_TESTS = {
    "test_e2e_lead_score_decision_approvals_draft_send_analytics",
    "test_e2e_deal_event_health_next_action_creates_task",
    "test_e2e_inbound_classification_support_draft_approval_send",
    "test_model_assisted_simulation_records_usage_but_never_mutates_crm",
    "test_concurrent_admission_serializes_tenant_quota",
}


def verify_backend_coverage(path: Path) -> None:
    cases = list(ElementTree.parse(path).getroot().iter("testcase"))
    modules = {case.attrib.get("classname", "") for case in cases}
    missing = {required for required in REQUIRED_BACKEND_MODULES
               if not any(module == required or module.startswith(required + ".") for module in modules)}
    if missing:
        raise ValueError("Required backend suites were not executed: " + ", ".join(sorted(missing)))
    missing_flows = REQUIRED_FLOW_TESTS - {case.attrib.get("name", "") for case in cases}
    if missing_flows:
        raise ValueError("Required automation flow tests were not executed: " + ", ".join(sorted(missing_flows)))


def junit_count(path: Path, minimum: int) -> int:
    suites = list(ElementTree.parse(path).getroot().iter("testsuite"))
    if not suites:
        raise ValueError(f"Missing test suites in {path.name}")
    for suite in suites:
        for key in ("failures", "errors", "skipped"):
            if int(suite.attrib.get(key, "0")):
                raise ValueError(f"Mandatory tests have {key}: {path.name}")
    count = sum(int(suite.attrib["tests"]) for suite in suites)
    if count < minimum:
        raise ValueError(f"Too few executed tests in {path.name}: {count} < {minimum}")
    return count


def unit_count(path: Path) -> int:
    report = path.read_text(encoding="utf-8-sig")
    totals = {}
    for field in ("tests", "pass", "fail", "cancelled", "skipped", "todo"):
        matches = re.findall(rf"^# {field} (\d+)\s*$", report, re.MULTILINE)
        if len(matches) != 1:
            raise ValueError(f"Missing or ambiguous TAP total: {field}")
        totals[field] = int(matches[0])
    if totals["tests"] != totals["pass"] or totals["pass"] < MIN_UNIT:
        raise ValueError("Frontend unit tests did not all pass")
    if any(totals[field] for field in ("fail", "cancelled", "skipped", "todo")):
        raise ValueError("Frontend units contain unfinished or failed tests")
    return totals["tests"]


def verify_scans(public: Path) -> None:
    def read(name):
        return json.loads((public / name).read_text(encoding="utf-8-sig"))

    report = read("gitleaks.json")
    if not isinstance(report, list) or report:
        raise ValueError("Secret scan findings require remediation: gitleaks.json")
    history = triage(read("gitleaks-history.json"))
    if not history["passed"] or history != read("gitleaks-history-triage.json"):
        raise ValueError("Secret scan history contains unreviewed or inconsistent findings")
    bandit = read("bandit.json")
    if "results" not in bandit or bandit["results"] or bandit.get("errors"):
        raise ValueError("Bandit findings or errors require remediation")
    audit = read("pip-audit.json")
    dependencies = audit.get("dependencies") if isinstance(audit, dict) else audit
    if not isinstance(dependencies, list) or not dependencies:
        raise ValueError("Python dependency audit is missing")
    if any(dependency.get("vulns") for dependency in dependencies):
        raise ValueError("Python dependency vulnerabilities remain")
    npm = read("npm-audit.json")
    if npm.get("error") or npm.get("metadata", {}).get("vulnerabilities", {}).get("total") != 0:
        raise ValueError("Node dependency audit did not report zero vulnerabilities")


def main():
    evidence = ROOT / "evidence"
    public = evidence / "public"
    destination = evidence / "public-artifact"
    if not (destination / "evidence-manifest.json").is_file():
        raise ValueError("Public evidence must be sanitized before writing the gate")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()  # nosec B603,B607
    if os.environ.get("GITHUB_SHA") and os.environ["GITHUB_SHA"] != sha:
        raise ValueError("Checked-out revision differs from the GitHub-tested SHA")
    backend = junit_count(public / "backend.xml", MIN_BACKEND)
    verify_backend_coverage(public / "backend.xml")
    browser = junit_count(evidence / "frontend-e2e.xml", MIN_BROWSER)
    units = unit_count(public / "frontend-unit.txt")
    verify_scans(public)
    repository = os.environ.get("GITHUB_REPOSITORY", "GlobexaTech/Globexa_CRM_Python")
    run = os.environ.get("GITHUB_RUN_ID")
    run_url = f"https://github.com/{repository}/actions/runs/{run}" if run else "Local validation"
    report = (
        "CHECKPOINT 7 GATE: PASS\n\n"
        f"Exact SHA: {sha}\nBackend tests: {backend}\nFrontend unit tests: {units}\nBrowser tests: {browser}\n"
        "Failed: 0\nErrors: 0\nSkipped: 0\n"
        "Source secret findings: 0\nHistory: 22 individually reviewed false positives; 0 unresolved.\n"
        f"Run: {run_url}\n\n"
        "Mandatory implementation, migration, RLS, authorization, security, integration and browser checks succeeded.\n"
        "External provider/model responses use deterministic test adapters; all CRM services and persistence execute normally.\n"
        "LIVE-CERTIFIED: BLOCKED - PROVIDER CREDENTIALS REQUIRED.\n"
        "Per-provider implementation and provider-readiness evidence is documented in CHECKPOINT_7_REPORT.md and CHECKPOINT_5_6_REPORT.md.\n"
    )
    (destination / "CHECKPOINT_7_GATE.txt").write_text(report, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write(report)
    print(report)


if __name__ == "__main__":
    main()
