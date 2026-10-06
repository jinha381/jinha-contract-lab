"""A5: UNKNOWN 판정 제거가 최종 판단에 미치는 영향을 비교한다."""

import json
from pathlib import Path

from verify import verdict

CASES = {
    "U1": Path("research/evidence/u1-002-insufficient-observation.json"),
    "U2": Path("research/evidence/u2-ambiguous-approval.json"),
    "U3": Path("research/evidence/u3-missing-approval-history.json"),
}


def force_binary(result, unknown_as):
    """UNKNOWN을 PASS 또는 FAIL로 강제 변환한다."""
    if result["verdict"] == "UNKNOWN":
        return unknown_as
    return result["verdict"]


def main():
    print("=== A5 UNKNOWN 제거 실험 ===")
    print()

    for name, path in CASES.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        result = verdict(data)

        forced_pass = force_binary(result, "PASS")
        forced_fail = force_binary(result, "FAIL")

        print(f"[{name}]")
        print(f"원래 M2      : {result['verdict']}")
        print(f"UNKNOWN→PASS : {forced_pass}")
        print(f"UNKNOWN→FAIL : {forced_fail}")

        if result["reasons"]:
            print(f"사유          : {result['reasons'][0]['detail']}")

        print()


if __name__ == "__main__":
    main()