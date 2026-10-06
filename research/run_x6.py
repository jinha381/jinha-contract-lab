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

        # X6: 승인 없는 출금 후 동일 금액 재입금
        "A": [],
        "H": [],

        "L": [],
        "T": [],

        "coverage_complete": False,

        "capture": {
            "rpc": args.rpc,
            "commitment": "finalized",
            "start_slot": balance["context"]["slot"],
            "scenario": "X6 unauthorized withdrawal and redeposit",
            "counterparty": args.recipient
        },

        "evidence_note":
            "X6 출금 후 재입금 실험. "
            "승인 A/H가 없는 상태에서 관리지갑에서 외부지갑으로 출금한 뒤 "
            "동일 외부지갑에서 동일 금액을 관리지갑으로 재입금한다."
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

    print(f"X6 관측 시작: {args.output}")
    print(
        f"시작 {evidence['C']['start']} | "
        f"slot {balance['context']['slot']} | "
        f"{balance['value']} lamports"
    )
    print(f"관리지갑: {args.wallet}")
    print(f"상대지갑: {args.recipient}")
    print("승인 A/H는 생성하지 않았습니다.")
    print("1단계: 관리지갑에서 상대지갑으로 0.05 SOL을 출금하세요.")
    print("2단계: 상대지갑에서 관리지갑으로 동일한 0.05 SOL을 재입금하세요.")


def finalize(args):
    """무승인 출금 후 동일 금액 재입금(X6) 거래 2건을 수집한다."""
    data = json.loads(args.evidence.read_text(encoding="utf-8"))

    if data.get("T") or data.get("L") or data["C"].get("closing") is not None:
        raise SystemExit("이미 완료된 증거 파일입니다. 덮어쓰지 않습니다.")

    url = data["capture"]["rpc"]
    wallet = data["C"]["wallet"]
    config = {
        "encoding": "jsonParsed",
        "commitment": "finalized",
        "maxSupportedTransactionVersion": 0
    }

    transactions = []

    for signature in args.signatures:
        detail = None

        for _ in range(15):
            detail = rpc(url, "getTransaction", [signature, config])
            if detail is not None:
                break
            time.sleep(2)

        if detail is None:
            raise SystemExit(f"finalized 거래가 아직 조회되지 않습니다: {signature}")

        message = detail["transaction"]["message"]
        instructions = message.get("instructions", [])

        transfers = [
            i["parsed"]["info"]
            for i in instructions
            if i.get("program") == "system"
            and i.get("parsed", {}).get("type") == "transfer"
        ]

        if len(instructions) != 1 or len(transfers) != 1 or detail.get("blockTime") is None:
            raise SystemExit(f"단일 System Program transfer가 아닙니다: {signature}")

        transfer = transfers[0]

        transaction = {
            "txid": signature,
            "from": transfer["source"],
            "to": transfer["destination"],
            "amount": transfer["lamports"],
            "time": stamp(datetime.fromtimestamp(detail["blockTime"], timezone.utc)),
            "status": "failed" if detail["meta"]["err"] else "success",
            "fee": detail["meta"]["fee"] if transfer["source"] == wallet else 0,
            "asset": "SOL",
            "_slot": detail["slot"]
        }

        transactions.append(transaction)

    withdrawal = transactions[0]
    redeposit = transactions[1]

    if withdrawal["from"] != wallet:
        raise SystemExit("첫 번째 거래가 관리지갑에서 출금된 거래가 아닙니다.")

    if redeposit["to"] != wallet:
        raise SystemExit("두 번째 거래가 관리지갑으로 재입금된 거래가 아닙니다.")

    if withdrawal["to"] != redeposit["from"]:
        raise SystemExit("출금 수신주소와 재입금 송신주소가 일치하지 않습니다.")

    if withdrawal["amount"] != redeposit["amount"]:
        raise SystemExit("출금 금액과 재입금 금액이 일치하지 않습니다.")

    if withdrawal["status"] != "success" or redeposit["status"] != "success":
        raise SystemExit("두 거래 중 실패한 거래가 있습니다.")

    if withdrawal["_slot"] >= redeposit["_slot"]:
        raise SystemExit("재입금이 출금보다 먼저 발생했습니다. Signature 순서를 확인하세요.")

    closing_response = rpc(
        url,
        "getBalance",
        [wallet, {"commitment": "finalized"}]
    )

    closing_slot = closing_response["context"]["slot"]

    if closing_slot < redeposit["_slot"]:
        raise SystemExit("기말 잔액 스냅샷이 재입금 거래보다 이전입니다. finalize를 다시 시도하세요.")

    first_available = rpc(url, "getFirstAvailableBlock")

    signatures = rpc(
        url,
        "getSignaturesForAddress",
        [wallet, {"limit": 1000, "commitment": "finalized"}]
    )

    start_slot = data["capture"]["start_slot"]

    in_window = [
        item
        for item in signatures
        if start_slot < item["slot"] <= closing_slot
    ]

    observed = {item["signature"] for item in in_window}
    expected = set(args.signatures)

    coverage = (
        first_available <= start_slot
        and len(signatures) < 1000
        and observed == expected
    )

    transactions.sort(key=lambda t: (t["time"], t["_slot"], t["txid"]))

    for transaction in transactions:
        transaction.pop("_slot")

    data["C"]["end"] = stamp(chain_time(url))
    data["C"]["closing"] = closing_response["value"]

    data["T"] = transactions

    # X6에서는 관리 실행기록이 존재하지 않는 무승인 출금을 재현한다.
    data["L"] = []

    data["coverage_complete"] = coverage

    data["capture"].update({
        "end_slot": closing_slot,
        "transaction_slots": [
            item["slot"]
            for item in in_window
            if item["signature"] in expected
        ],
        "first_available_block": first_available,
        "signature_count": len(signatures),
        "signatures_in_window": in_window,
        "signature_limit": 1000
    })

    data["evidence_note"] = (
        "관리대상 지갑에서 승인 없이 자산이 출금된 후 "
        "동일 수신주소에서 동일 금액이 관리대상 지갑으로 재입금된 X6 시나리오입니다. "
        "기말 자산 규모는 수수료를 제외하면 회복되지만 관찰기간 중 무승인 출금이 존재합니다."
    )

    args.evidence.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )

    m1_result = verdict(data, baseline=True)
    m2_result = verdict(data)

    print()
    print(f"무승인 출금 TXID: {args.signatures[0]}")
    print(f"재입금 TXID: {args.signatures[1]}")
    print(f"기초잔액: {data['C']['opening']} lamports")
    print(f"기말잔액: {data['C']['closing']} lamports")
    print(f"잔액차이: {data['C']['closing'] - data['C']['opening']} lamports")

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

    start.add_argument("recipient",  help="counterparty wallet public address")

    start.add_argument("--case-id", default="localnet-X6-001")

    start.add_argument(
        "--rpc",
        default="http://127.0.0.1:18999"
    )

    start.add_argument("--output", type=Path, default=Path("research/evidence/x6-withdraw-redeposit.json"))

    finish = sub.add_parser(
        "finalize",
        help="collect unauthorized withdrawal"
    )

    finish.add_argument(
        "evidence",
        type=Path
    )

    finish.add_argument("signatures", nargs=2)

    args = parser.parse_args()

    if args.command == "prepare":
        prepare(args)
    else:
        finalize(args)


if __name__ == "__main__":
    main()