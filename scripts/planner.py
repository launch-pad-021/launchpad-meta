#!/usr/bin/env python3
"""Validate a planner proposal; publishing is deliberately a separate trusted job."""

import argparse
import json
import sys

from agent_control import PolicyError, validate_plan_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?", default="-")
    args = parser.parse_args()
    stream = sys.stdin if args.manifest == "-" else open(args.manifest, encoding="utf-8")
    try:
        manifest = json.load(stream)
        order = validate_plan_manifest(manifest)
    except (OSError, json.JSONDecodeError, PolicyError) as error:
        print(json.dumps({"valid": False, "reason": str(error)}))
        return 2
    finally:
        if stream is not sys.stdin:
            stream.close()
    print(json.dumps({"valid": True, "order": order}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
