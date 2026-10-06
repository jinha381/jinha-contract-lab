"""User-run X1: unauthorized SOL withdrawal without approval.

The script records the observation window before the transfer,
then collects the manually generated transaction and compares M1/M2.
It never signs or sends SOL.
"""

import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from verify import verdict


def stamp(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def rpc(url, method, params=None):
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or []
    }).encode()

    request = urllib.request.Request(
        url,
        payload,
        {"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        answer = json.load(response)

    if "error" in answer:
        raise RuntimeError(f"{method}: {answer['error']}")

    return answer["result"]


def chain_time(url):
    slot = rpc(
        url,
        "getSlot",
        [{"commitment": "finalized"}]
    )

    block_time = rpc(
        url,
        "getBlockTime",
        [slot]
    )

    if block_time is None:
        raise RuntimeError(
            "현재 finalized slot의 blockTime을 조회할 수 없습니다."
        )

    return datetime.fromtimestamp(
        block_time,
        timezone.utc
    )


def prepare(args):
    if args.output.exists():
        raise SystemExit(
            f"파일이 이미 있습니다: {args.output}. "
            "새 --output 경로를 사용하세요."
        )

    balance = rpc(
        args.rpc,
        "getBalance",
        [args.wallet, {"commitment": "finalized"}]
    )

    now = chain_time(args.rpc)

    evidence = {
        "C": {
            "case_id": args.case_id,
            "wallet": args.wallet,
            "asset": "SOL",
            "start": stamp(now),
            "end": None,
            "opening": balance["value"],
            "closing": None
        },

        # X1의 핵심:
        # 출금 승인이 존재하지 않는다.
        "A": [],
        "H": [],

        "L": [],
        "T": [],

        "coverage_complete": False,

        "capture": {
            "rpc": args.rpc,
            "commitment": "finalized",
            "start_slot": balance["context"]["slot"],
            "scenario": "X1 unauthorized withdrawal"
        },

        "evidence_note":
            "X1 승인 없는 출금 실험. "
            "A/H를 생성하지 않은 상태에서 관리지갑의 출금을 수행한다."
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    args.output.write_text(
        json.dumps(
            evidence,
            ensure_ascii=False,
            indent=2
        ) + "\n",
        encoding="utf-8"
    )

    print(f"X1 관측 시작: {args.output}")
    print(
        f"시작 {evidence['C']['start']} | "
        f"slot {balance['context']['slot']} | "
        f"{balance['value']} lamports"
    )
    print(f"관리지갑: {args.wallet}")
    print("승인 A/H는 생성하지 않았습니다.")
    print("이제 관리지갑에서 외부지갑으로 SOL을 전송하세요.")


def finalize(args):
    data = json.loads(
        args.evidence.read_text(encoding="utf-8")
    )

    if (
        data.get("T")
        or data.get("L")
        or data["C"].get("closing") is not None
    ):
        raise SystemExit(
            "이미 완료된 증거 파일입니다. 덮어쓰지 않습니다."
        )

    url = data["capture"]["rpc"]
    wallet = data["C"]["wallet"]

    config = {
        "encoding": "jsonParsed",
        "commitment": "finalized",
        "maxSupportedTransactionVersion": 0
    }

    detail = None

    for _ in range(15):
        detail = rpc(
            url,
            "getTransaction",
            [args.signature, config]
        )

        if detail is not None:
            break

        time.sleep(2)

    if detail is None:
        raise SystemExit(
            "finalized 거래가 아직 조회되지 않습니다. "
            "잠시 후 같은 finalize 명령을 다시 실행하세요."
        )

    message = detail["transaction"]["message"]
    instructions = message.get("instructions", [])

    transfers = [
        i["parsed"]["info"]
        for i in instructions
        if i.get("program") == "system"
        and i.get("parsed", {}).get("type") == "transfer"
    ]

    if (
        len(instructions) != 1
        or len(transfers) != 1
        or detail.get("blockTime") is None
    ):
        raise SystemExit(
            "단일 System Program transfer가 아닙니다. "
            "자동 X1 수집을 중단합니다."
        )

    transfer = transfers[0]

    # X1은 관리지갑에서 나가는 출금이어야 한다.
    if transfer["source"] != wallet:
        raise SystemExit(
            "선택한 거래의 송신주소가 관리지갑이 아닙니다. "
            "X1 출금 Signature를 확인하세요."
        )

    transaction = {
        "txid": args.signature,
        "from": transfer["source"],
        "to": transfer["destination"],
        "amount": transfer["lamports"],
        "time": stamp(
            datetime.fromtimestamp(
                detail["blockTime"],
                timezone.utc
            )
        ),
        "status": (
            "failed"
            if detail["meta"]["err"]
            else "success"
        ),

        # 관리지갑이 송신자이므로 실제 fee 반영
        "fee": detail["meta"]["fee"],

        "asset": "SOL"
    }

    closing_response = rpc(
        url,
        "getBalance",
        [wallet, {"commitment": "finalized"}]
    )

    closing_slot = closing_response["context"]["slot"]

    if closing_slot < detail["slot"]:
        raise SystemExit(
            "기말 잔액 스냅샷이 거래 슬롯보다 이전입니다."
        )

    first_available = rpc(
        url,
        "getFirstAvailableBlock"
    )

    signatures = rpc(
        url,
        "getSignaturesForAddress",
        [
            wallet,
            {
                "limit": 1000,
                "commitment": "finalized"
            }
        ]
    )

    start_slot = data["capture"]["start_slot"]

    in_window = [
        item
        for item in signatures
        if start_slot < item["slot"] <= closing_slot
    ]

    observed = {
        item["signature"]
        for item in in_window
    }

    expected = (
        transaction["from"] == wallet
        and transaction["status"] == "success"
    )

    coverage = (
        first_available <= start_slot
        and len(signatures) < 1000
        and observed == {args.signature}
        and expected
    )

    data["C"]["end"] = stamp(
        chain_time(url)
    )

    data["C"]["closing"] = (
        closing_response["value"]
    )

    data["T"] = [transaction]

    # 실제 거래가 발생했으므로 실행기록 L은 존재.
    # 단, 승인 자체가 없으므로 approval_id는 None.
    data["L"] = [{
        "id": "execution-" + data["C"]["case_id"],
        "approval_id": None,
        "txid": args.signature,
        "result": transaction["status"],
        "time": stamp(chain_time(url))
    }]

    data["coverage_complete"] = coverage

    data["capture"].update({
        "end_slot": closing_slot,
        "transaction_slot": detail["slot"],
        "first_available_block": first_available,
        "signature_count": len(signatures),
        "signatures_in_window": in_window,
        "signature_limit": 1000
    })

    data["evidence_note"] = (
        "X1 승인 없는 출금. "
        "A/H 없이 실제 출금 T가 발생했으며 "
        "실행기록 L과 transaction fee를 포함하여 검증한다."
    )

    args.evidence.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ) + "\n",
        encoding="utf-8"
    )

    # M1 / M2 모두 계산
    m1_result = verdict(
        data,
        baseline=True
    )

    m2_result = verdict(data)

    print(f"TXID {args.signature}")
    print(
        f"출금 {transaction['time']} | "
        f"slot {detail['slot']} | "
        f"{transaction['amount']} lamports | "
        f"fee {transaction['fee']} lamports"
    )

    print(
        f"기초잔액 {data['C']['opening']} lamports"
    )

    print(
        f"기말잔액 {data['C']['closing']} lamports"
    )

    print(
        f"관측구간 서명 {len(in_window)}개"
    )

    print(
        f"첫 보관 블록 {first_available} | "
        f"시작 slot {start_slot} | "
        f"coverage {coverage}"
    )

    print()
    print("=== M1 ===")
    print(f"verdict: {m1_result['verdict']}")
    print(f"reasons: {m1_result['reasons']}")

    print()
    print("=== M2 ===")
    print(f"verdict: {m2_result['verdict']}")
    print(f"checks: {m2_result['checks']}")
    print(f"reasons: {m2_result['reasons']}")

    print()
    print(f"saved: {args.evidence}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True
    )

    start = sub.add_parser(
        "prepare",
        help="start X1 observation"
    )

    start.add_argument(
        "wallet",
        help="custody wallet public address"
    )

    start.add_argument(
        "--case-id",
        default="localnet-X1-001"
    )

    start.add_argument(
        "--rpc",
        default="http://127.0.0.1:18999"
    )

    start.add_argument(
        "--output",
        type=Path,
        default=Path(
            "research/evidence/x1-unauthorized.json"
        )
    )

    finish = sub.add_parser(
        "finalize",
        help="collect unauthorized withdrawal"
    )

    finish.add_argument(
        "evidence",
        type=Path
    )

    finish.add_argument(
        "signature"
    )

    args = parser.parse_args()

    if args.command == "prepare":
        prepare(args)
    else:
        finalize(args)


if __name__ == "__main__":
    main()