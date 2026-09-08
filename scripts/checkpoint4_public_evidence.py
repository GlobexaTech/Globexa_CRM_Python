"""Copy a strict, redacted CI evidence allowlist without altering source files.

Run after browser/scanner steps and before writing the exact-SHA gate marker.
Private fixtures, runtime environments, server logs, HTML reports, DOM snapshots,
traces and videos are never copied. Only test screenshots are copied as binary.
"""
import json
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
DESTINATION = EVIDENCE / "public-artifact"
PUBLIC_FILES = {
    "backend.xml", "backend.txt", "migrations.txt", "ruff.txt", "bandit.json",
    "pip-audit.json", "openapi.txt", "eslint.txt", "typecheck.txt", "build.txt",
    "npm-audit.json", "frontend-unit.txt", "auth-unit.txt", "frontend-e2e.txt", "gitleaks.json",
}
AUDIT_SCREENSHOT = re.compile(
    r"(?:dashboard|leads|contacts|companies|pipeline|tasks|conversations|campaigns|"
    r"automations|integrations|ai-agents|analytics|search|settings|help|customers|"
    r"lead-drawer)-(?:1440|1280|768|390)\.png$"
)
SECRET_NAME = re.compile(r"(?:KEY|SECRET|PASSWORD|TOKEN)$", re.IGNORECASE)
JWT = re.compile(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{16,}(?![A-Za-z0-9_-])")
OPAQUE_IDENTIFIER = re.compile(r"(?<![a-fA-F0-9])[a-fA-F0-9]{64}(?![a-fA-F0-9])")


def load_private(name):
    path = EVIDENCE / name
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise RuntimeError("Private evidence metadata is unreadable; refusing to publish") from None


def sensitive_values():
    values = set()
    runtime = load_private("runtime.env.json")
    for key, value in {**os.environ, **runtime}.items():
        if isinstance(value, str) and value and SECRET_NAME.search(key):
            values.add(value)
        if isinstance(value, str) and key.endswith("_URL"):
            try:
                password = urlsplit(value).password
                if password:
                    values.update({password, unquote(password)})
            except ValueError:
                pass
    fixture = load_private("fixture.json")
    for user in fixture.get("users", {}).values():
        if isinstance(user, dict) and isinstance(user.get("password"), str):
            values.add(user["password"])
    return sorted((value for value in values if value), key=len, reverse=True)


def redact(value, secrets):
    for secret in secrets:
        value = value.replace(secret, "[REDACTED]")
    value = JWT.sub("[REDACTED_JWT]", value)
    return OPAQUE_IDENTIFIER.sub("[REDACTED_OPAQUE_ID]", value)


def public_copy(source, destination, secrets):
    if source.is_symlink() or not source.resolve().is_relative_to(EVIDENCE.resolve()):
        raise RuntimeError("Evidence source must remain inside the evidence directory")
    if source.stat().st_size > 20 * 1024 * 1024:
        raise RuntimeError("Evidence file exceeds the bounded publication size")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(redact(source.read_text(encoding="utf-8-sig"), secrets), encoding="utf-8")


def audit_screenshot(relative):
    # Only deliberate screenshots taken after the audit verifies an authenticated
    # product view may leave the runner. Generic failure screenshots can show a
    # login/private form even when their spec name is not auth.spec.ts.
    return (
        len(relative.parts) == 2
        and relative.parts[0].startswith("accessibility-")
        and bool(AUDIT_SCREENSHOT.fullmatch(relative.name))
    )


def main():
    secrets = sensitive_values()
    if DESTINATION.is_symlink() or not DESTINATION.resolve().is_relative_to(EVIDENCE.resolve()):
        raise RuntimeError("Public evidence destination must remain inside evidence")
    DESTINATION.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in sorted(PUBLIC_FILES):
        source = EVIDENCE / "public" / name
        if source.is_file():
            public_copy(source, DESTINATION / name, secrets)
            copied.append(name)
    browser_xml = EVIDENCE / "frontend-e2e.xml"
    if browser_xml.is_file():
        public_copy(browser_xml, DESTINATION / "frontend-e2e.xml", secrets)
        copied.append("frontend-e2e.xml")
    screenshot_root = EVIDENCE / "playwright-results"
    if screenshot_root.is_dir():
        for source in sorted(screenshot_root.rglob("*.png")):
            relative = source.relative_to(screenshot_root)
            if not audit_screenshot(relative):
                continue
            if source.is_symlink() or not source.resolve().is_relative_to(screenshot_root.resolve()):
                raise RuntimeError("Screenshot must remain inside the test output directory")
            image = source.read_bytes()
            if len(image) > 20 * 1024 * 1024 or not image.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("Invalid or oversized screenshot")
            target = DESTINATION / "screenshots" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(image)
            copied.append(str(target.relative_to(DESTINATION)).replace("\\", "/"))
    manifest = {
        "files": copied,
        "redaction": "Private fixture/runtime values, JWTs and 64-character hexadecimal opaque IDs removed from text.",
        "screenshots": "Explicit authenticated audit screenshots of synthetic CRM fixtures only; generic failure/auth screenshots, DOM snapshots, HTML, logs, traces and videos excluded.",
    }
    (DESTINATION / "evidence-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Prepared {len(copied)} allowlisted public evidence files; private sources remain unchanged.")


if __name__ == "__main__":
    main()
