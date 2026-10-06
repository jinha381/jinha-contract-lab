"""Localnet X5 experiment: mismatch between on-chain transaction T and execution log L."""

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from verify import verdict


def rpc(url, method, params=None):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode()
    request = Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urlopen(request) as response:
        result = json.loads(response.read().decode())
    if "error" in result:
        raise RuntimeError(result["error"])
    return result["result"]


def stamp(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def chain_time(url):
    slot = rpc(url, "getSlot", [{"commitment": "finalized"}])
    block_time = rpc(url, "getBlockTime", [slot])
    if block_time is None:
        raise RuntimeError("현재 finalized slot의 blockTime을 조회할 수 없습니다.")
    return datetime.fromtimestamp(block_time, timezone.utc)


def prepare(args):
    if args.output.exists():
        raise SystemExit(f"이미 파일이 존재합니다: {args.output}")

    url = args.rpc
    approved_at = chain_time(url)
    balance_response = rpc(url, "getBalance", [args.wallet, {"commitment": "finalized"}])
    start_slot = balance_response["context"]["slot"]
    opening = balance_response["value"]
    approval_id = "approval-" + args.case_id

    data = {
        "C": {
            "case_id": args.case_id,
            "wallet": args.wallet,
            "asset": "SOL",
            "start": stamp(approved_at),
            "end": None,
            "opening": opening,
            "closing": None
        },
        "A": [{
            "id": approval_id,
            "recipient": args.recipient,
            "amount": args.amount,
            "valid_from": stamp(approved_at),
            "valid_until": stamp(approved_at + timedelta(hours=1)),
            "use_limit": 1
        }],
        "H": [{"approval_id": approval_id, "state": "active", "time": stamp(approved_at)}],
        "L": [],
        "T": [],
        "coverage_complete": False,
        "rpc_error": False,
        "capture": {
            "rpc": url,
            "start_slot": start_slot
        }
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"X5 실행기록 불일치 실험 시작: {args.output}")
    print(f"시작 {stamp(approved_at)} | slot {start_slot} | {opening} lamports")
    print(f"승인 금액 {args.amount} lamports | 수신주소 {args.recipient}")
    print("승인 상태: active | use_limit=1")
    print("이제 승인과 동일한 조건으로 SOL을 1회 이전하세요.")


def finalize(args):
    data = json.loads(args.evidence.read_text(encoding="utf-8"))

    if data.get("T") or data.get("L") or data["C"].get("closing") is not None:
        raise SystemExit("이미 완료된 증거 파일입니다. 덮어쓰지 않습니다.")

    url = data["capture"]["rpc"]
    wallet = data["C"]["wallet"]
    approval = data["A"][0]
    config = {"encoding": "jsonParsed", "commitment": "finalized", "maxSupportedTransactionVersion": 0}

    detail = None
    for _ in range(15):
        detail = rpc(url, "getTransaction", [args.signature, config])
        if detail is not None:
            break
        time.sleep(2)

    if detail is None:
        raise SystemExit("finalized 거래가 아직 조회되지 않습니다. 잠시 후 같은 finalize 명령을 다시 실행하세요.")

    message = detail["transaction"]["message"]
    instructions = message.get("instructions", [])
    transfers = [i["parsed"]["info"] for i in instructions if i.get("program") == "system" and i.get("parsed", {}).get("type") == "transfer"]

    if len(instructions) != 1 or len(transfers) != 1 or detail.get("blockTime") is None:
        raise SystemExit("단일 System Program transfer가 아닙니다. 자동 X5 수집을 중단합니다.")

    transfer = transfers[0]

    transaction = {
        "txid": args.signature,
        "from": transfer["source"],
        "to": transfer["destination"],
        "amount": transfer["lamports"],
        "time": stamp(datetime.fromtimestamp(detail["blockTime"], timezone.utc)),
        "status": "failed" if detail["meta"]["err"] else "success",
        "fee": detail["meta"]["fee"] if transfer["source"] == wallet else 0,
        "asset": "SOL"
    }

    if transaction["from"] != wallet or transaction["to"] != approval["recipient"] or transaction["amount"] != approval["amount"] or transaction["status"] != "success":
        raise SystemExit("X5 승인 조건과 일치하지 않는 거래입니다.")

    closing_response = rpc(url, "getBalance", [wallet, {"commitment": "finalized"}])
    closing_slot = closing_response["context"]["slot"]

    if closing_slot < detail["slot"]:
        raise SystemExit("기말 잔액 스냅샷이 거래 슬롯보다 이전입니다. finalize를 다시 시도하세요.")

    first_available = rpc(url, "getFirstAvailableBlock")
    signatures = rpc(url, "getSignaturesForAddress", [wallet, {"limit": 1000, "commitment": "finalized"}])
    start_slot = data["capture"]["start_slot"]
    in_window = [item for item in signatures if start_slot < item["slot"] <= closing_slot]
    observed = {item["signature"] for item in in_window}

    coverage = first_available <= start_slot and len(signatures) < 1000 and observed == {args.signature}

    data["C"]["end"] = stamp(chain_time(url))
    data["C"]["closing"] = closing_response["value"]
    data["T"] = [transaction]

    fake_txid = "mismatch-" + args.signature

    data["L"] = [{
        "id": "execution-" + data["C"]["case_id"],
        "approval_id": approval["id"],
        "txid": fake_txid,
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

    data["evidence_note"] = "X5 실험을 위해 온체인 거래 T는 실제 TXID를 기록하고, 실행기록 L에는 의도적으로 다른 TXID를 기록했습니다."

    args.evidence.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    m1_result = verdict(data, baseline=True)
    m2_result = verdict(data)

    print()
    print(f"실제 T.txid: {args.signature}")
    print(f"기록 L.txid: {fake_txid}")

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
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("prepare")
    start.add_argument("wallet")
    start.add_argument("recipient")
    start.add_argument("--amount", type=int, default=50000000)
    start.add_argument("--case-id", default="localnet-X5-001")
    start.add_argument("--rpc", default="http://127.0.0.1:18999")
    start.add_argument("--output", type=Path, default=Path("research/evidence/x5-execution-mismatch.json"))

    finish = sub.add_parser("finalize")
    finish.add_argument("evidence", type=Path)
    finish.add_argument("signature")

    args = parser.parse_args()

    if args.command == "prepare":
        prepare(args)
    else:
        finalize(args)


if __name__ == "__main__":
    main()