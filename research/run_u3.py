"""U3: 승인 상태 이력 부족으로 실행 시점의 승인 상태를 확인할 수 없는 상황을 검증한다."""

import argparse
import json
from copy import deepcopy
from pathlib import Path

from verify import verdict


def run(args):
    source = json.loads(args.source.read_text(encoding="utf-8"))
    data = deepcopy(source)

    data["C"]["case_id"] = args.case_id

    # U3의 유일한 실험 변수:
    # 승인 A는 유지하되 승인 상태 이력 H를 제거한다.
    data["H"] = []

    data["evidence_note"] = (
        "U3 승인 상태 이력 부족 실험. 정상 N2 증거 묶음을 기준으로 "
        "승인 기록 A와 거래·실행기록은 유지하되 승인 상태 이력 H만 제거하여, "
        "거래 실행 시점의 승인 활성 상태를 확인할 수 없는 상황을 구성하였다."
    )

    if args.output.exists():
        raise SystemExit(
            f"파일이 이미 있습니다: {args.output}. "
            "새 --output 경로를 사용하세요."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )

    source_m2 = verdict(source)
    u3_m1 = verdict(data, baseline=True)
    u3_m2 = verdict(data)

    print(f"기준 증거: {args.source}")
    print(f"U3 증거: {args.output}")

    print()
    print("=== 기준 N2 ===")
    print(f"M2 verdict: {source_m2['verdict']}")

    print()
    print("=== U3 ===")
    print(f"승인 수: {len(data['A'])}")
    print(f"승인 상태 이력 수: {len(data['H'])}")

    print()
    print("M1")
    print(f"verdict: {u3_m1['verdict']}")
    print(f"reasons: {u3_m1['reasons']}")

    print()
    print("M2")
    print(f"verdict: {u3_m2['verdict']}")
    print(f"checks: {u3_m2['checks']}")
    print(f"reasons: {u3_m2['reasons']}")

    print()
    print(f"saved: {args.output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "source",
        type=Path,
        help="정상 N2 evidence JSON"
    )

    parser.add_argument(
        "--case-id",
        default="localnet-U3-001"
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/evidence/u3-missing-approval-history.json")
    )

    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()