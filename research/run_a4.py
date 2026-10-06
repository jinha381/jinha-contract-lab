"""A4: 명시적 승인 연결정보 제거가 승인 식별에 미치는 영향을 검증한다."""

import argparse
import json
from copy import deepcopy
from pathlib import Path

from verify import verdict


def run(args):
    source = json.loads(args.source.read_text(encoding="utf-8"))
    data = deepcopy(source)

    data["C"]["case_id"] = args.case_id

    # 기존 승인과 조건이 동일한 두 번째 승인 후보를 추가한다.
    original = data["A"][0]
    duplicate = deepcopy(original)
    duplicate["id"] = f"approval-{args.case_id}-duplicate"
    data["A"].append(duplicate)

    # 두 번째 승인에도 동일한 active 이력을 추가한다.
    data["H"].append({
        "approval_id": duplicate["id"],
        "state": "active",
        "time": duplicate["valid_from"]
    })

    # 중요:
    # L.approval_id는 제거하지 않는다.
    # 전체 모델에서는 이 명시적 연결정보를 이용해 원래 승인을 특정할 수 있다.

    data["evidence_note"] = (
        "A4 명시적 승인 연결정보 제거 실험. 정상 N2 증거에 거래 조건이 동일한 "
        "두 번째 승인 후보를 추가하되 실행기록의 approval_id는 유지하였다. "
        "전체 모델과 explicit_link 제거 모델의 판정 차이를 비교한다."
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

    full = verdict(data)
    ablated = verdict(data, omit={"explicit_link"})

    print(f"기준 증거: {args.source}")
    print(f"A4 증거: {args.output}")

    print()
    print("=== A4 구성 ===")
    print(f"승인 후보 수: {len(data['A'])}")
    print(f"L.approval_id: {[l.get('approval_id') for l in data['L']]}")

    print()
    print("전체 M2")
    print(f"verdict: {full['verdict']}")
    print(f"checks: {full['checks']}")
    print(f"reasons: {full['reasons']}")

    print()
    print("explicit_link 제거")
    print(f"verdict: {ablated['verdict']}")
    print(f"checks: {ablated['checks']}")
    print(f"reasons: {ablated['reasons']}")

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
        default="localnet-A4-001"
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/evidence/a4-explicit-link.json")
    )

    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()