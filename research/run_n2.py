"""User-run N2: record approval before a manual SOL transfer, then verify it.

This script reads RPC and writes evidence JSON. It never signs or sends SOL.
"""

import argparse
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from verify import verdict


def stamp(value=None):
    return (value or datetime.now(timezone.utc)).isoformat(timespec="seconds").replace("+00:00", "Z")


def rpc(url, method, params=None):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode()
    request = urllib.request.Request(url, payload, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        answer = json.load(response)
    if "error" in answer:
        raise RuntimeError(f"{method}: {answer['error']}")
    return answer["result"]


def prepare(args):
    if args.output.exists():
        raise SystemExit(f"파일이 이미 있습니다: {args.output}. 새 --output 경로를 사용하세요.")
    if args.amount <= 0:
        raise SystemExit("승인 금액은 양수 lamports여야 합니다.")
    balance = rpc(args.rpc, "getBalance", [args.wallet, {"commitment": "finalized"}])
    if balance["value"] <= args.amount + 5000:
        raise SystemExit("지갑 잔액이 승인금액과 예상 수수료보다 작습니다.")
    now = datetime.now(timezone.utc)
    approval_id = "approval-" + args.case_id
    evidence = {
        "C": {"case_id": args.case_id, "wallet": args.wallet, "asset": "SOL", "start": stamp(now), "end": None, "opening": balance["value"], "closing": None},
        "A": [{"id": approval_id, "amount": args.amount, "recipient": args.recipient, "valid_from": stamp(now), "valid_until": stamp(now + timedelta(minutes=10)), "use_limit": 1}],
        "H": [{"approval_id": approval_id, "state": "active", "time": stamp(now)}],
        "L": [], "T": [], "coverage_complete": False,
        "capture": {"rpc": args.rpc, "commitment": "finalized", "start_slot": balance["context"]["slot"], "approval_recorded_before_transfer": True},
        "evidence_note": "승인 A/H를 거래 전에 저장했습니다. 실행기록 L은 거래 후 연구자가 기록합니다. 완료 전 판정은 UNKNOWN입니다."
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"승인 기록: {args.output}")
    print(f"시작 {evidence['C']['start']} | slot {balance['context']['slot']} | {balance['value']} lamports")
    print(f"승인 금액 {args.amount} lamports | 수신주소 {args.recipient}")
    print("이제 수동으로 SOL을 이전하고 출력된 Signature를 finalize 명령에 사용하세요.")


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
        raise SystemExit("단일 System Program transfer가 아닙니다. 자동 N2 수집을 중단합니다.")
    transfer = transfers[0]
    transaction = {"txid": args.signature, "from": transfer["source"], "to": transfer["destination"], "amount": transfer["lamports"], "time": stamp(datetime.fromtimestamp(detail["blockTime"], timezone.utc)), "status": "failed" if detail["meta"]["err"] else "success", "fee": detail["meta"]["fee"] if transfer["source"] == wallet else 0, "asset": "SOL"}
    closing_response = rpc(url, "getBalance", [wallet, {"commitment": "finalized"}])
    closing_slot = closing_response["context"]["slot"]
    if closing_slot < detail["slot"]:
        raise SystemExit("기말 잔액 스냅샷이 거래 슬롯보다 이전입니다. finalize를 다시 시도하세요.")
    first_available = rpc(url, "getFirstAvailableBlock")
    signatures = rpc(url, "getSignaturesForAddress", [wallet, {"limit": 1000, "commitment": "finalized"}])
    start_slot = data["capture"]["start_slot"]
    in_window = [item for item in signatures if start_slot < item["slot"] <= closing_slot]
    observed = {item["signature"] for item in in_window}
    expected = transaction["from"] == wallet and transaction["to"] == approval["recipient"] and transaction["amount"] == approval["amount"] and transaction["status"] == "success"
    coverage = first_available <= start_slot and len(signatures) < 1000 and observed == {args.signature} and expected
    data["C"]["end"] = stamp()
    data["C"]["closing"] = closing_response["value"]
    data["T"] = [transaction]
    data["L"] = [{"id": "execution-" + data["C"]["case_id"], "approval_id": approval["id"], "txid": args.signature, "result": transaction["status"], "time": stamp()}]
    data["coverage_complete"] = coverage
    data["capture"].update({"end_slot": closing_slot, "transaction_slot": detail["slot"], "first_available_block": first_available, "signature_count": len(signatures), "signatures_in_window": in_window, "signature_limit": 1000})
    data["evidence_note"] = "승인 A/H는 거래 전, 실행기록 L은 거래 후 작성했습니다. coverage는 ledger 보관 범위와 관측구간 서명으로 확인합니다."
    args.evidence.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = verdict(data)
    print(f"TXID {args.signature}")
    print(f"거래 {transaction['time']} | slot {detail['slot']} | fee {transaction['fee']} lamports")
    print(f"기말 잔액 {closing_response['value']} lamports | 관측구간 서명 {len(in_window)}개")
    print(f"첫 보관 블록 {first_available} | 시작 slot {start_slot} | coverage {coverage}")
    print(f"M2 verdict: {result['verdict']}")
    print(f"saved: {args.evidence}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("prepare", help="write A/H before manually sending SOL")
    start.add_argument("wallet")
    start.add_argument("recipient")
    start.add_argument("--amount", type=int, default=50_000_000, help="lamports; default 0.05 SOL")
    start.add_argument("--case-id", default="localnet-N2-001")
    start.add_argument("--rpc", default="http://127.0.0.1:18999")
    start.add_argument("--output", type=Path, default=Path("research/evidence/n2-approved.json"))
    finish = sub.add_parser("finalize", help="collect transaction and record execution after manual transfer")
    finish.add_argument("evidence", type=Path)
    finish.add_argument("signature")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
    else:
        finalize(args)


if __name__ == "__main__":
    main()
