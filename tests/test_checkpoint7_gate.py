from xml.etree import ElementTree as ET
import pytest
from scripts import checkpoint7_gate as gate


def coverage_file(tmp_path, names):
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite", tests=str(len(names)), errors="0", failures="0", skipped="0")
    for module in gate.REQUIRED_BACKEND_MODULES:
        ET.SubElement(suite, "testcase", classname=module, name="test_module")
    for name in names: ET.SubElement(suite, "testcase", classname="tests.test_checkpoint7_engine", name=name)
    target = tmp_path / "backend.xml"
    ET.ElementTree(root).write(target)
    return target


def test_gate_rejects_module_presence_without_required_flows(tmp_path):
    with pytest.raises(ValueError, match="flow tests"):
        gate.verify_backend_coverage(coverage_file(tmp_path, set()))


def test_gate_accepts_all_required_automation_evidence(tmp_path):
    gate.verify_backend_coverage(coverage_file(tmp_path, gate.REQUIRED_FLOW_TESTS))


@pytest.mark.parametrize("omitted", sorted(gate.REQUIRED_FLOW_TESTS))
def test_gate_rejects_missing_individual_flow(tmp_path, omitted):
    with pytest.raises(ValueError, match="flow tests"):
        gate.verify_backend_coverage(coverage_file(tmp_path, gate.REQUIRED_FLOW_TESTS - {omitted}))
