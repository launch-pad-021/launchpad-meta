#!/usr/bin/env python3
"""Deduplicate typed weekly findings without granting the model write access."""

import hashlib
import json
import sys


ALLOWED_AUDITORS = {"security-auditor", "docs-auditor", "dependency-auditor", "spec-drift-auditor"}


def fingerprint(finding):
    required = ("auditor", "repo", "rule", "path", "summary")
    if not isinstance(finding, dict) or any(not isinstance(finding.get(key), str) for key in required):
        raise ValueError("malformed-finding")
    if finding["auditor"] not in ALLOWED_AUDITORS:
        raise ValueError("unknown-auditor")
    material = "\0".join(finding[key] for key in required).encode()
    return hashlib.sha256(material).hexdigest()


def main() -> int:
    try:
        findings = json.load(sys.stdin)
        output = []
        seen = set()
        for finding in findings:
            key = fingerprint(finding)
            if key not in seen:
                seen.add(key)
                output.append({"fingerprint": key, **finding})
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
