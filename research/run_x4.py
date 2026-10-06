"""n2를 x2에 맞추어 편집
"""

import argparse
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from verify import verdict


def stamp(value=None):
    """UTC 시각을 비교 가능한 초 단위 ISO 8601 문자열로 만든다."""
    return (value or datetime.now(timezone.utc)).isoformat(timespec="seconds").replace("+00:00", "Z")


def rpc(url, method, params=None):
    """Solana JSON-RPC 결과만 반환하고 RPC 오류는 예외로 전달한다."""
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode()
    request = urllib.request.Request(url, payload, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        answer = json.load(response)
    if "error" in answer:
        raise RuntimeError(f"{method}: {answer['error']}")
    return answer["result"]

def chain_time(url):
    slot = rpc(url, "getSlot", [{"commitment": "finalized"}])
    block_time = rpc(url, "getBlockTime", [slot])

    if block_time is None:
        raise RuntimeError("현재 finalized slot의 blockTime을 조회할 수 없습니다.")

    return datetime.fromtimestamp(block_time, timezone.utc)

def next_chain_time(url, previous):
    while True:
        current = chain_time(url)
        if current > previous:
            return current
        time.sleep(0.2)

def prepare(args):
    """기초잔액·시작 슬롯과 거래 전 승인 A/H를 새 증거 파일에 기록한다."""
    # 기존 파일은 덮어쓰지 않는다. 사전 승인 시각의 증거를 보존하기 위해서다.
    if args.output.exists():
        raise SystemExit(f"파일이 이미 있습니다: {args.output}. 새 --output 경로를 사용하세요.")
    if args.amount <= 0:
        raise SystemExit("승인 금액은 양수 lamports여야 합니다.")
    # 승인 금액 외에 예상 수수료 5,000 lamports를 낼 잔액도 확인한다.
    # 실제 수수료는 finalize에서 온체인 meta.fee를 읽는다.
    balance = rpc(args.rpc, "getBalance", [args.wallet, {"commitment": "finalized"}])
    if balance["value"] <= args.amount + 5000:
        raise SystemExit("지갑 잔액이 승인금액과 예상 수수료보다 작습니다.")
    now = chain_time(args.rpc)
    approval_id = "approval-" + args.case_id
    # 준비 단계에서는 종료 시각·기말잔액·L/T가 아직 없다.
    # coverage_complete=False로 저장해 완료 전 PASS가 나오지 않게 한다.
    approved_at = chain_time(args.rpc)
    evidence = {
        "C": {"case_id": args.case_id, "wallet": args.wallet, "asset": "SOL", "start": stamp(now), "end": None, "opening": balance["value"], "closing": None},
        "A": [{"id": approval_id, "amount": args.amount, "recipient": args.recipient, "valid_from": stamp(now), "valid_until": stamp(now + timedelta(hours=1)), "use_limit": 1}],
        "H": [{"approval_id": approval_id, "state": "active", "time": stamp(approved_at)}],
        "L": [], "T": [], "coverage_complete": False,
        "capture": {"rpc": args.rpc, "commitment": "finalized", "start_slot": balance["context"]["slot"], "approval_recorded_before_transfer": True},
        "evidence_note": "승인 A/H를 거래 전에 저장했습니다. 실행기록 L은 거래 후 연구자가 기록합니다. 완료 전 판정은 UNKNOWN입니다."
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"재사용 실험 승인 기록: {args.output}")
    print(f"승인 금액 {args.amount} lamports | 수신주소 {args.recipient} | use_limit=1")
    print("동일한 승인 조건으로 SOL을 2회 이전한 뒤 두 Signature를 finalize에 사용하세요.")

#x4에 맞게 파이널라이즈 재정의
def finalize(args):
    """두 TXID를 수집하여 동일 승인의 2회 사용(X4) 증거를 완성한다."""
    data = json.loads(args.evidence.read_text(encoding="utf-8"))
    if data.get("T") or data.get("L") or data["C"].get("closing") is not None:
        raise SystemExit("이미 완료된 증거 파일입니다. 덮어쓰지 않습니다.")

    url = data["capture"]["rpc"]
    wallet = data["C"]["wallet"]
    approval = data["A"][0]
    config = {"encoding": "jsonParsed", "commitment": "finalized", "maxSupportedTransactionVersion": 0}
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
        transfers = [i["parsed"]["info"] for i in instructions if i.get("program") == "system" and i.get("parsed", {}).get("type") == "transfer"]
        if len(instructions) != 1 or len(transfers) != 1 or detail.get("blockTime") is None:
            raise SystemExit(f"단일 System Program transfer가 아닙니다: {signature}")

        transfer = transfers[0]
        transaction = {"txid": signature, "from": transfer["source"], "to": transfer["destination"], "amount": transfer["lamports"], "time": stamp(datetime.fromtimestamp(detail["blockTime"], timezone.utc)), "status": "failed" if detail["meta"]["err"] else "success", "fee": detail["meta"]["fee"] if transfer["source"] == wallet else 0, "asset": "SOL"}

        if transaction["from"] != wallet or transaction["to"] != approval["recipient"] or transaction["amount"] != approval["amount"] or transaction["status"] != "success":
            raise SystemExit(f"X4 승인 조건과 일치하지 않는 거래입니다: {signature}")

        transaction["_slot"] = detail["slot"]
        transactions.append(transaction)

    transactions.sort(key=lambda t: (t["time"], t["_slot"], t["txid"]))

    closing_response = rpc(url, "getBalance", [wallet, {"commitment": "finalized"}])
    closing_slot = closing_response["context"]["slot"]
    last_transaction_slot = max(t["_slot"] for t in transactions)
    if closing_slot < last_transaction_slot:
        raise SystemExit("기말 잔액 스냅샷이 마지막 거래 슬롯보다 이전입니다. finalize를 다시 시도하세요.")

    first_available = rpc(url, "getFirstAvailableBlock")
    signatures = rpc(url, "getSignaturesForAddress", [wallet, {"limit": 1000, "commitment": "finalized"}])
    start_slot = data["capture"]["start_slot"]
    in_window = [item for item in signatures if start_slot < item["slot"] <= closing_slot]
    observed = {item["signature"] for item in in_window}
    expected_signatures = set(args.signatures)
    coverage = first_available <= start_slot and len(signatures) < 1000 and observed == expected_signatures

    for transaction in transactions:
        transaction.pop("_slot")

    data["C"]["end"] = stamp(chain_time(url))
    data["C"]["closing"] = closing_response["value"]
    data["T"] = transactions
    data["L"] = [{"id": f"execution-{data['C']['case_id']}-{i+1}", "approval_id": approval["id"], "txid": transaction["txid"], "result": transaction["status"], "time": transaction["time"]} for i, transaction in enumerate(transactions)]
    data["coverage_complete"] = coverage
    data["capture"].update({"end_slot": closing_slot, "transaction_slots": [item["slot"] for item in in_window if item["signature"] in expected_signatures], "first_available_block": first_available, "signature_count": len(signatures), "signatures_in_window": in_window, "signature_limit": 1000})
    data["evidence_note"] = "하나의 승인(use_limit=1)에 대해 동일 조건의 거래를 2회 실행했습니다. 두 거래 모두 동일 approval_id와 연결합니다."
    args.evidence.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    m1_result = verdict(data, baseline=True)
    m2_result = verdict(data)

    print()
    print("=== M1 ===")
    print(f"verdict: {m1_result['verdict']}")
    print(f"reasons: {m1_result['reasons']}")
    print()
    print("=== M2 ===")
    print(f"verdict: {m2_result['verdict']}")
    print(f"checks: {m2_result['checks']}")
    print(f"reasons: {m2_result['reasons']}")


def main():
    """prepare/finalize 두 명령의 인자를 해석해 해당 단계만 실행한다."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("prepare", help="write A/H before manually sending SOL")
    start.add_argument("wallet")
    start.add_argument("recipient")
    start.add_argument("--amount", type=int, default=50_000_000, help="lamports; default 0.05 SOL")
    start.add_argument("--case-id", default="localnet-X4-001")
    start.add_argument("--rpc", default="http://127.0.0.1:18999")
    start.add_argument("--output", type=Path, default=Path("research/evidence/x4-approval-reuse.json"))
    finish = sub.add_parser("finalize", help="collect transaction and record execution after manual transfer")
    finish.add_argument("evidence", type=Path)
    finish.add_argument("signatures", nargs=2)
    # x4를 위한 특별 수정
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
    else:
        finalize(args)


if __name__ == "__main__":
    main()
