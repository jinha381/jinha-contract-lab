"""지정 관리지갑의 네이티브 SOL 이전 거래를 Localnet RPC에서 수집한다.

범용 수집 보조 도구다. 시작·종료 잔액, 관측범위, 누락 서명을 자동으로
증명하지 못하므로 출력 JSON의 coverage_complete는 항상 False로 둔다.
"""

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def main():
    """공개주소의 거래 서명을 조회하고 단일 SOL 이전만 JSON으로 저장한다."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("wallet")
    p.add_argument("--rpc", default="http://127.0.0.1:8899")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--output", type=Path, default=Path("research/localnet-evidence.json"))
    args = p.parse_args()
    counter = 0

    def rpc(method, params):
        """요청마다 다른 id를 붙여 JSON-RPC를 호출하고 오류를 전파한다."""
        nonlocal counter
        counter += 1
        body = json.dumps({"jsonrpc": "2.0", "id": counter, "method": method, "params": params}).encode()
        with urllib.request.urlopen(urllib.request.Request(args.rpc, body, {"Content-Type": "application/json"}), timeout=15) as response:
            result = json.load(response)
        if "error" in result:
            raise RuntimeError(result["error"])
        return result["result"]

    # 주소를 참조한 서명을 조회한다. limit에 도달하거나 ledger가 과거
    # 블록을 정리한 경우 이 목록만으로 전체 이력을 보증할 수 없다.
    signatures = rpc("getSignaturesForAddress", [args.wallet, {"limit": args.limit}])
    transfers = []
    skipped = []
    # RPC의 최신순 결과를 시간순으로 처리한다. 거래 상세가 없거나
    # 범위 밖 instruction이면 skipped_signatures에 남겨 수동 검토하게 한다.
    for item in reversed(signatures):
        detail = rpc("getTransaction", [item["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        if detail is None or item.get("blockTime") is None:
            skipped.append(item["signature"])
            continue
        instructions = detail["transaction"]["message"]["instructions"]
        native = [ix for ix in instructions if ix.get("program") == "system" and ix.get("parsed", {}).get("type") == "transfer"]
        if len(native) != 1 or len(instructions) != 1:
            skipped.append(item["signature"])
            continue
        # JSON-RPC parsed transfer의 lamports와 메타 수수료를 T로 옮긴다.
        # 수수료는 관리지갑이 송신자일 때만 그 지갑의 감소분에 해당한다.
        info = native[0]["parsed"]["info"]
        transfers.append({"txid": item["signature"], "from": info["source"], "to": info["destination"], "amount": info["lamports"], "time": datetime.fromtimestamp(item["blockTime"], timezone.utc).isoformat().replace("+00:00", "Z"), "status": "failed" if detail["meta"]["err"] else "success", "fee": detail["meta"]["fee"] if info["source"] == args.wallet else 0, "asset": "SOL"})
    # C의 사건번호·관측 시각·잔액과 A/H/L은 실제 실험 기록으로 채워야 한다.
    # 여기서는 판정 준비가 끝나지 않았으므로 coverage_complete=False다.
    evidence = {"C": {"case_id": "EDIT_ME", "wallet": args.wallet, "asset": "SOL", "start": "EDIT_ME", "end": "EDIT_ME", "opening": 0, "closing": 0}, "A": [], "H": [], "L": [], "T": transfers, "coverage_complete": False, "capture": {"rpc": args.rpc, "signature_count": len(signatures), "limit": args.limit, "skipped_signatures": skipped}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"captured {len(transfers)} transfers; skipped {len(skipped)} signatures; review {args.output}")


if __name__ == "__main__":
    main()
