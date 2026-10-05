"""N1(거래 없음)을 사용자가 실행할 때 잔액·슬롯·거래 이력을 기록한다.

서명이나 송금은 하지 않는다. Localnet ledger가 오래된 거래를 정리하기 전에
관측 종료 직후 RPC 증거를 수집하도록 한 명령으로 절차를 묶었다.
"""

import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from verify import verdict


def utc_now():
    """결과 JSON과 화면에 기록할 현재 시각을 UTC 초 단위로 반환한다."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def rpc(url, method, params=None):
    """로컬 validator의 JSON-RPC를 호출하고 오류 응답을 예외로 처리한다."""
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode()
    request = urllib.request.Request(url, payload, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)
    if "error" in data:
        raise RuntimeError(f"{method}: {data['error']}")
    return data["result"]


def main():
    """확정 잔액 두 번과 관측구간 서명 목록을 수집해 N1을 평가한다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wallet", help="public address of the funded N1 custody wallet")
    parser.add_argument("--rpc", default="http://127.0.0.1:18999")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--output", type=Path, default=Path("research/evidence/n1-rerun.json"))
    args = parser.parse_args()
    if args.seconds < 10:
        parser.error("--seconds must be at least 10")
    if args.output.exists():
        parser.error(f"output already exists: {args.output}; choose a new --output")

    # 기초잔액과 그 응답의 finalized 슬롯을 한 쌍으로 기록한다.
    # 이 슬롯보다 나중이며 종료 슬롯 이하인 거래가 N1의 관측 대상이다.
    balance_params = [args.wallet, {"commitment": "finalized"}]
    opening_response = rpc(args.rpc, "getBalance", balance_params)
    opening = opening_response["value"]
    start_slot = opening_response["context"]["slot"]
    start_time = utc_now()
    print(f"START {start_time} | finalized slot {start_slot} | {opening} lamports", flush=True)
    print("관측 중: 이 지갑으로 거래를 보내지 마세요.", flush=True)
    # 진행 시간을 보여 주되 이 구간에는 지갑 거래를 만들지 않는다.
    remaining = args.seconds
    while remaining > 0:
        step = min(10, remaining)
        time.sleep(step)
        remaining -= step
        print(f"  {args.seconds - remaining}/{args.seconds}초", flush=True)

    # 기말잔액과 종료 슬롯을 읽은 즉시 이력 보관 범위·서명을 조회한다.
    closing_response = rpc(args.rpc, "getBalance", balance_params)
    closing = closing_response["value"]
    end_slot = closing_response["context"]["slot"]
    end_time = utc_now()
    print(f"END   {end_time} | finalized slot {end_slot} | {closing} lamports", flush=True)

    first_available = rpc(args.rpc, "getFirstAvailableBlock")
    signatures = rpc(args.rpc, "getSignaturesForAddress", [args.wallet, {"limit": 1000, "commitment": "finalized"}])
    # 조회 제한 1000건에 닿거나 첫 보관 블록이 시작 슬롯보다 늦으면
    # '거래 없음'을 증명할 수 없으므로 coverage_complete를 False로 둔다.
    in_window = [item for item in signatures if start_slot < item["slot"] <= end_slot]
    coverage_complete = first_available <= start_slot and len(signatures) < 1000 and end_slot > start_slot and not in_window
    evidence = {
        "C": {"case_id": "localnet-N1-rerun", "wallet": args.wallet, "asset": "SOL", "start": start_time, "end": end_time, "opening": opening, "closing": closing},
        "A": [], "H": [], "L": [], "T": [],
        "coverage_complete": coverage_complete,
        "expected_verdict": "PASS",
        "capture": {"rpc": args.rpc, "commitment": "finalized", "start_slot": start_slot, "end_slot": end_slot, "first_available_block": first_available, "signature_limit": 1000, "signature_count": len(signatures), "signatures_in_window": in_window},
        "evidence_note": "N1 관측은 잔액 스냅샷 사이의 슬롯과 거래 서명을 확인합니다. 범위 보존·조회 완전성이 부족하거나 거래가 관측되면 UNKNOWN으로 보류합니다."
    }
    # 원본 관측값을 증거 JSON에 남기고 공통 검증기의 M2 판정을 출력한다.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = verdict(evidence)
    print(f"ledger first available block: {first_available}")
    print(f"signatures in window: {len(in_window)}")
    print(f"M2 verdict: {result['verdict']}")
    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()
