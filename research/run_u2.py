"""U2: 복수의 승인 후보로 인해 거래-승인 연결이 모호한 상태를 검증한다."""

import argparse
import json
from copy import deepcopy
from pathlib import Path

from verify import verdict


def run(args):
    source = json.loads(args.source.read_text(encoding="utf-8"))
    data = deepcopy(source)

    data["C"]["case_id"] = args.case_id

    # 기존 정상 승인 A1을 복제하여
    # 금액·수신주소·유효기간이 동일한 두 번째 승인 A2를 만든다.
    original = data["A"][0]
    duplicate = deepcopy(original)
    duplicate["id"] = f"approval-{args.case_id}-duplicate"
    data["A"].append(duplicate)

    # 두 번째 승인에 대해서도 동일한 active 이력을 추가한다.
    duplicate_history = {
        "approval_id": duplicate["id"],
        "state": "active",
        "time": duplicate["valid_from"]
    }
    data["H"].append(duplicate_history)

    # 실행기록에서 명시적인 approval_id 연결을 제거한다.
    # 따라서 거래 조건만으로는 A1/A2 중 어느 승인을 사용했는지 특정할 수 없다.
    for log in data["L"]:
        log["approval_id"] = None

    data["evidence_note"] = (
        "U2 승인 연결 모호성 실험. 정상 N2 증거를 기준으로 동일한 금액, "
        "수신주소 및 유효조건을 가진 승인 후보를 하나 추가하고 실행기록의 "
        "명시적 approval_id 연결을 제거하여 거래가 어느 승인에 대응하는지 "
        "특정할 수 없는 상태를 구성하였다."
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
    u2_m1 = verdict(data, baseline=True)
    u2_m2 = verdict(data)

    print(f"기준 증거: {args.source}")
    print(f"U2 증거: {args.output}")

    print()
    print("=== 기준 N2 ===")
    print(f"M2 verdict: {source_m2['verdict']}")

    print()
    print("=== U2 ===")
    print(f"승인 후보 수: {len(data['A'])}")
    print(f"L.approval_id: {[l.get('approval_id') for l in data['L']]}")

    print()
    print("M1")
    print(f"verdict: {u2_m1['verdict']}")
    print(f"reasons: {u2_m1['reasons']}")

    print()
    print("M2")
    print(f"verdict: {u2_m2['verdict']}")
    print(f"checks: {u2_m2['checks']}")
    print(f"reasons: {u2_m2['reasons']}")

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
        default="localnet-U2-001"
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/evidence/u2-ambiguous-approval.json")
    )

    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()