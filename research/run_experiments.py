"""논문의 통제된 합성 시나리오와 정보·규칙 제거 실험을 재현한다.

이 파일의 지갑주소·TXID·승인기록은 모두 가상 값이다. Localnet 실측 결과와
혼동하지 않도록 results.json에도 합성 자료임을 명시한다.
"""

import copy
import json
from pathlib import Path

from verify import verdict


def base():
    """거래가 없고 잔액이 일정한 기본 C/A/H/L/T 증거 묶음을 만든다."""
    return {"C": {"case_id": "case-001", "wallet": "custody", "asset": "SOL", "start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z", "opening": 100000, "closing": 100000}, "A": [], "H": [], "L": [], "T": [], "coverage_complete": True}


def tx(txid="tx1", src="custody", dst="recipient", amount=1000, time="2026-01-01T12:00:00Z"):
    """합성 SOL 이전 한 건을 만든다. 관리지갑이 송신자일 때만 수수료를 부담한다."""
    return {"txid": txid, "from": src, "to": dst, "amount": amount, "time": time, "status": "success", "fee": 10 if src == "custody" else 0, "asset": "SOL"}


def approved():
    """N2의 기본형인 승인 1건·정상 출금 1건·실행기록 1건을 만든다."""
    b = base()
    b["T"] = [tx()]
    b["C"]["closing"] = 98990
    b["A"] = [{"id": "a1", "amount": 1000, "recipient": "recipient", "valid_from": "2026-01-01T00:00:00Z", "valid_until": "2026-01-02T00:00:00Z", "use_limit": 1}]
    b["H"] = [{"approval_id": "a1", "state": "active", "time": "2026-01-01T00:00:00Z"}]
    b["L"] = [{"id": "l1", "approval_id": "a1", "txid": "tx1", "result": "success", "time": "2026-01-01T12:01:00Z"}]
    return b


def cases():
    """N(정상), X(불일치), U(판단보류) 12개 사례와 기대판정을 돌려준다."""
    # N1~N3: 거래 없음, 승인 출금, 외부지갑 입금.
    n1 = base()
    n2 = approved()
    n3 = base(); n3["T"] = [tx(src="outside", dst="custody")]; n3["L"] = [{"id": "l1", "txid": "tx1", "result": "success"}]; n3["C"]["closing"] = 101000
    # X1~X6: 승인 부재·조건 차이·취소·재사용·실행기록 차이·출금 후 재입금.
    x1 = approved(); x1["A"] = []; x1["H"] = []
    x2 = approved(); x2["A"][0]["amount"] = 999
    x3 = approved(); x3["H"].append({"approval_id": "a1", "state": "cancelled", "time": "2026-01-01T11:00:00Z"})
    x4 = approved(); x4["T"].append(tx("tx2", time="2026-01-01T13:00:00Z")); x4["L"].append({"id": "l2", "approval_id": "a1", "txid": "tx2", "result": "success"}); x4["C"]["closing"] = 97980
    x5 = approved(); x5["L"][0]["result"] = "failed"
    x6 = base(); x6["T"] = [tx(), tx("tx2", "outside", "custody", 1010, "2026-01-01T13:00:00Z")]; x6["L"] = [{"id": "l1", "txid": "tx1", "result": "success"}, {"id": "l2", "txid": "tx2", "result": "success"}]
    # U1~U3: 온체인 관측 불완전, 승인 연결 모호성, 승인 상태 이력 누락.
    u1 = approved(); u1["coverage_complete"] = False
    u2 = approved(); u2["A"].append({**u2["A"][0], "id": "a2"}); u2["H"].append({"approval_id": "a2", "state": "active", "time": "2026-01-01T00:00:00Z"}); u2["L"][0].pop("approval_id")
    u3 = approved(); u3["H"] = []
    return {"N1": (n1, "PASS"), "N2": (n2, "PASS"), "N3": (n3, "PASS"), "X1": (x1, "FAIL"), "X2": (x2, "FAIL"), "X3": (x3, "FAIL"), "X4": (x4, "FAIL"), "X5": (x5, "FAIL"), "X6": (x6, "FAIL"), "U1": (u1, "UNKNOWN"), "U2": (u2, "UNKNOWN"), "U3": (u3, "UNKNOWN")}


def run():
    """M1/M2 비교 및 A1~A5 제거 실험 결과를 JSON과 화면에 출력한다."""
    # 기대판정은 판정 함수와 독립적으로 사례를 만들 때 미리 지정했다.
    rows = []
    for name, (data, expected) in cases().items():
        m1, m2 = verdict(data, True), verdict(data)
        rows.append({"id": name, "expected": expected, "M1": m1["verdict"], "M2": m2["verdict"], "checks": m2["checks"], "reasons": m2["reasons"]})
    # A1~A3: 같은 증거에서 입력 필드 또는 R3 검사만 제거한다.
    ablations = {}
    for label, name, omit in [("A1", "X3", ["H"]), ("A2", "X4", ["use_limit"]), ("A3", "X5", ["R3"])]:
        data = copy.deepcopy(cases()[name][0])
        ablations[label] = {"case": name, "original": verdict(data)["verdict"], "ablated": verdict(data, omit=omit)["verdict"]}
    # A4: 승인 두 건의 조건이 같아도 명시적 연결정보가 있으면 구별된다.
    # 연결정보를 빼면 어느 승인을 사용했는지 확정할 수 없다.
    connected = approved()
    connected["A"].append({**connected["A"][0], "id": "a2"})
    connected["H"].append({"approval_id": "a2", "state": "active", "time": "2026-01-01T00:00:00Z"})
    disconnected = copy.deepcopy(connected)
    disconnected["L"][0].pop("approval_id")
    ablations["A4"] = {"case": "two_matching_approvals", "original": verdict(connected)["verdict"], "ablated": verdict(disconnected)["verdict"]}
    # A5: 본래 UNKNOWN이어야 할 사례를 PASS/FAIL로 강제했을 때의
    # 근거 없는 확정판정 수를 각각 집계한다.
    unknown_cases = [row for row in rows if row["expected"] == "UNKNOWN"]
    ablations["A5a"] = {"cases": [row["id"] for row in unknown_cases], "forced": "PASS", "unsupported_decisions": len(unknown_cases)}
    ablations["A5b"] = {"cases": [row["id"] for row in unknown_cases], "forced": "FAIL", "unsupported_decisions": len(unknown_cases)}
    output = {"source": "synthetic evidence; not Solana Localnet observations", "cases": rows, "ablations": ablations}
    # 생성 결과는 연구 코드 옆의 results.json에 쓴다(.gitignore 대상).
    path = Path(__file__).parent / "results.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")
    for row in rows:
        print(f"{row['id']:>2} expected={row['expected']:<7} M1={row['M1']:<7} M2={row['M2']}")
    if any(r["expected"] != r["M2"] for r in rows):
        raise SystemExit("M2 differs from predeclared expectations")


if __name__ == "__main__":
    run()
