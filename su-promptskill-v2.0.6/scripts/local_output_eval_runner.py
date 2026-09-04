#!/usr/bin/env python3
"""Execute the 3.1.6 Chinese-semantic output case without external APIs."""

from __future__ import annotations

import json
from pathlib import Path
import sys


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = SKILL_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import prompt_skill as delivery


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Deterministic Output Eval runner; not a user-facing CLI."


def _grouping_decisions(source: dict[str, object]) -> dict[str, object]:
    normalized, _ = delivery.normalize_input(source)
    shots = normalized["shots"]
    compatibility = {key: True for key in delivery.COMPATIBILITY_KEYS}
    return {
        "grouping_review": {
            "contract": delivery.GROUPING_REVIEW_CONTRACT,
            "source_observed_hash": normalized["source"]["observed_content_hash"],
            "partition_policy": delivery.GROUPING_PARTITION_POLICY,
            "boundaries": [
                {
                    "left_source_shot_id": left["source_shot_id"],
                    "right_source_shot_id": right["source_shot_id"],
                    "compatibility": compatibility,
                    "classification": "prefer_join",
                    "semantic_evidence": ["same_scene"],
                    "reason": "同一场景内的来源动作与对白连续。",
                }
                for left, right in zip(shots, shots[1:])
            ],
        }
    }


def main() -> int:
    request = json.load(sys.stdin)
    if (
        request.get("case_id") != "director-316-chinese-semantic-forward"
        or request.get("variant") != "with_skill"
    ):
        output = str(request.get("fixture_output", ""))
    else:
        relative = Path(str(request["input_files"][0]))
        source_path = SKILL_ROOT / "evals" / "output" / relative
        source = delivery.load_json(source_path)
        plan = delivery.build_prompt_plan(
            source,
            decisions=_grouping_decisions(source),
            model_profile=delivery.resolve_model_profile(
                "seedance-2.5-default"
            ),
        )
        if plan["validation"]["status"] != "PASS":
            raise RuntimeError(json.dumps(plan["diagnostics"], ensure_ascii=False))
        output = "\n".join(
            unit["prompt_text"] for unit in plan["prompt_units"]
        )
    print(json.dumps({"output": output, "execution_kind": "command"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
