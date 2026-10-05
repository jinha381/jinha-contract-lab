"""논문의 C/A/H/L/T 증거 묶음에 M1 또는 M2 판정을 적용한다.

입력 JSON의 금액·수수료는 lamports 정수, 시각은 UTC ISO 8601 문자열이다.
이 모듈은 제공된 기록의 정합성만 계산한다. RPC 자료나 관리기록의 진위를
독립적으로 증명하지 않으므로 M2의 자료 충분성은 coverage_complete에 의존한다.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def verdict(bundle, baseline=False, omit=()):
    """증거 묶음을 평가해 최종 판정, 규칙별 상태, 구체적 사유를 반환한다.

    baseline=True는 기본 조건 비교(M1), 기본값은 R0~R4를 적용하는 M2다.
    omit은 승인 이력·사용횟수·R3 제거 실험에 사용한다.
    """
    # C/A/H/L/T는 각각 관리대상·승인·승인 이력·실행기록·온체인 거래다.
    c = bundle.get("C", {})
    approvals = bundle.get("A", [])
    history = bundle.get("H", [])
    logs = bundle.get("L", [])
    txs = bundle.get("T", [])
    omitted = set(omit)
    checks = {f"R{i}": "PASS" for i in range(5)}
    reasons = []

    def mark(rule, status, reason):
        """규칙의 상태를 기록한다. 같은 규칙에서는 확정된 FAIL을 유지한다."""
        if checks[rule] != "FAIL" or status == "FAIL":
            checks[rule] = status
        reasons.append({"rule": rule, "status": status, "detail": reason})

    # R0: 판단 전에 관리대상과 거래 자료가 충분한지 확인한다.
    # M1에는 coverage_complete 요구를 적용하지 않아 M1/M2의 차이를 볼 수 있다.
    required_c = ("case_id", "wallet", "asset", "start", "end", "opening", "closing")
    if any(k not in c for k in required_c) or not isinstance(txs, list):
        mark("R0", "UNKNOWN", "C or T is incomplete")
    if not baseline and (not bundle.get("coverage_complete", False) or bundle.get("rpc_error", False)):
        mark("R0", "UNKNOWN", "on-chain observation is incomplete")
    if checks["R0"] == "UNKNOWN":
        return {"verdict": "UNKNOWN", "checks": checks, "reasons": reasons}

    # 거래의 필수 필드 누락·중복 TXID는 연결 자체가 불명확하므로 보류한다.
    required_t = ("txid", "from", "to", "amount", "time", "status", "fee")
    if any(not isinstance(t, dict) or any(k not in t for k in required_t) for t in txs):
        mark("R0", "UNKNOWN", "transaction fields are incomplete")
    ids = [t["txid"] for t in txs if isinstance(t, dict) and "txid" in t]
    if len(ids) != len(set(ids)):
        mark("R0", "UNKNOWN", "duplicate transaction identifier")
    if checks["R0"] == "UNKNOWN":
        return {"verdict": "UNKNOWN", "checks": checks, "reasons": reasons}

    # R1: 모든 거래가 지정 지갑·자산·관측기간에 속하는지 확인한다.
    # 승인 검사는 관리지갑에서 성공적으로 출금된 거래에만 적용한다.
    wallet = c["wallet"]
    outgoing = []
    for t in txs:
        if not (c["start"] <= t["time"] <= c["end"]) or t.get("asset", "SOL") != c["asset"]:
            mark("R1", "FAIL", f"transaction outside managed scope: {t['txid']}")
        if wallet not in (t["from"], t["to"]):
            mark("R1", "FAIL", f"unrelated transaction: {t['txid']}")
        if t["from"] == wallet and t["status"] == "success":
            outgoing.append(t)

    # R2: 금액과 수신주소로 승인 후보를 찾고 L의 승인번호로 후보를 좁힌다.
    # 후보가 둘 이상이면 임의로 선택하지 않고 R0 UNKNOWN으로 처리한다.
    used = defaultdict(int)
    for t in sorted(outgoing, key=lambda x: (x["time"], x["txid"])):
        candidates = [a for a in approvals if a.get("recipient") == t["to"] and a.get("amount") == t["amount"]]
        linked = [l for l in logs if l.get("txid") == t["txid"]]
        explicit = {l.get("approval_id") for l in linked if l.get("approval_id")}
        if explicit:
            candidates = [a for a in candidates if a.get("id") in explicit]
        if len(candidates) > 1 and not baseline:
            mark("R0", "UNKNOWN", f"ambiguous approval for {t['txid']}")
            continue
        if not candidates:
            mark("R2", "FAIL", f"no matching approval for {t['txid']}")
            continue
        a = candidates[0]
        if not baseline:
            # 거래 시점의 유효기간, 허용 사용횟수, 가장 최근 승인 상태를 확인한다.
            if not (a.get("valid_from", "") <= t["time"] <= a.get("valid_until", "")):
                mark("R2", "FAIL", f"approval expired or not yet valid: {a['id']}")
            if "use_limit" in omitted or "use_limit" not in a:
                mark("R0", "UNKNOWN", f"use limit unavailable: {a['id']}")
            else:
                used[a["id"]] += 1
                if used[a["id"]] > a["use_limit"]:
                    mark("R2", "FAIL", f"approval reused: {a['id']}")
            events = [h for h in history if h.get("approval_id") == a["id"] and h.get("time", "") <= t["time"]]
            if "H" in omitted or not events:
                mark("R0", "UNKNOWN", f"approval history unavailable: {a['id']}")
            elif max(events, key=lambda h: h["time"])["state"] != "active":
                mark("R2", "FAIL", f"approval inactive at execution: {a['id']}")

    # R3: 거래와 실행기록을 TXID로 양방향 대조한다.
    # 누락·중복 기록 또는 실행결과 불일치를 각각 구분해 남긴다.
    if not baseline and "R3" not in omitted:
        tx_by_id = {t.get("txid"): t for t in txs}
        for t in txs:
            matches = [l for l in logs if l.get("txid") == t.get("txid")]
            if len(matches) == 0:
                mark("R3", "FAIL", f"execution log missing: {t.get('txid')}")
            elif len(matches) > 1:
                mark("R0", "UNKNOWN", f"multiple logs for {t.get('txid')}")
            elif matches[0].get("result") != t.get("status"):
                mark("R3", "FAIL", f"execution result differs: {t.get('txid')}")
        for log in logs:
            if log.get("txid") not in tx_by_id:
                mark("R3", "FAIL", f"logged transaction not observed: {log.get('txid')}")

    # R4: 기초잔액 + 입금 - 출금 - 관리지갑 부담 수수료 = 기말잔액.
    # 실패한 출금 거래도 수수료를 부담할 수 있어 금액과 별도로 반영한다.
    if not baseline:
        expected = c["opening"]
        for t in txs:
            if t.get("status") == "success":
                if t.get("to") == wallet:
                    expected += t["amount"]
                if t.get("from") == wallet:
                    expected -= t["amount"] + t["fee"]
            elif t.get("from") == wallet:
                expected -= t.get("fee", 0)
        if expected != c["closing"]:
            mark("R4", "FAIL", f"computed closing {expected}, recorded {c['closing']}")

    # 자료가 부족하면 다른 규칙에서 차이를 보더라도 확정 판정을 강제하지 않는다.
    result = "UNKNOWN" if checks["R0"] == "UNKNOWN" else "FAIL" if "FAIL" in checks.values() else "PASS"
    return {"verdict": result, "checks": checks, "reasons": reasons}


def main():
    """CLI 인자를 읽어 JSON 증거 한 건의 판정을 표준 출력에 표시한다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--baseline", action="store_true", help="M1 basic approval conditions")
    parser.add_argument("--omit", action="append", choices=["H", "use_limit", "R3"])
    args = parser.parse_args()
    data = json.loads(args.evidence.read_text(encoding="utf-8"))
    print(json.dumps(verdict(data, args.baseline, args.omit or ()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
