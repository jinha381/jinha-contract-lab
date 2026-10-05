"""N3(외부지갑에서 관리지갑으로 정상 입금)의 증거를 수집한다.

prepare로 입금 전 기초잔액·시작 슬롯을 저장하고, 사용자가 송금한 뒤
finalize로 거래·기말잔액·ledger 보관 범위를 기록한다. 서명이나 송금은 하지 않는다.
"""

import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from verify import verdict


def stamp(value=None):
    """현재 또는 지정된 시각을 UTC ISO 8601 초 단위로 표시한다."""
    return (value or datetime.now(timezone.utc)).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def rpc(url, method, params=None):
    """JSON-RPC 호출 결과만 반환하며 서버 오류는 예외로 올린다."""
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


def prepare(args):
    """관측 시작 전에 확정 잔액과 시작 슬롯을 새 증거 JSON에 기록한다."""
    if args.output.exists():
        raise SystemExit(
            f"파일이 이미 있습니다: {args.output}. "
            "새 --output 경로를 사용하세요."
        )

    # 입금 전 잔액을 기준으로 삼고 같은 RPC 응답의 context.slot을 보존한다.
    balance = rpc(
        args.rpc,
        "getBalance",
        [args.wallet, {"commitment": "finalized"}]
    )

    now = datetime.now(timezone.utc)

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

        # N3는 외부지갑 → 관리지갑 정상 입금이므로
        # 출금 승인 A/H는 사용하지 않는다.
        "A": [],
        "H": [],

        "L": [],
        "T": [],

        # finalize 전에는 종료 자료가 없으므로 PASS 판정을 허용하지 않는다.
        "coverage_complete": False,

        "capture": {
            "rpc": args.rpc,
            "commitment": "finalized",
            "start_slot": balance["context"]["slot"],
            "deposit_recorded_before_transfer": True
        },

        "evidence_note":
            "N3 정상 입금 관측 시작. "
            "외부지갑에서 관리지갑으로 입금한 후 "
            "Signature를 finalize에 전달합니다."
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)

    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )

    print(f"N3 관측 시작: {args.output}")
    print(
        f"시작 {evidence['C']['start']} | "
        f"slot {balance['context']['slot']} | "
        f"{balance['value']} lamports"
    )
    print(f"관리지갑: {args.wallet}")
    print("이제 외부지갑에서 관리지갑으로 SOL을 전송하세요.")
    print("출력된 Signature를 finalize 명령에 사용하세요.")


def finalize(args):
    """입금 TXID를 조회해 증거를 완성하고 공통 검증기로 판정한다."""
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

    # 거래 직후에는 finalized 상태가 아닐 수 있어 짧게 재조회한다.
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

    # 실험 범위가 단일 System Program 이전이므로 다른 instruction이
    # 섞인 거래는 자동 판정 대상으로 삼지 않는다.
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
            "자동 N3 수집을 중단합니다."
        )

    transfer = transfers[0]

    # N3는 반드시 관리지갑으로 들어오는 거래여야 한다.
    if transfer["destination"] != wallet:
        raise SystemExit(
            "선택한 거래의 수신주소가 관리지갑이 아닙니다. "
            "N3 입금 거래 Signature를 확인하세요."
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

        # 송신자가 외부지갑이므로
        # 관리지갑의 자산흐름에서는 fee를 차감하지 않는다.
        "fee": 0,
        "asset": "SOL"
    }

    # 기말잔액의 finalized 슬롯이 거래 슬롯 이후여야 해당 입금이 반영된다.
    closing_response = rpc(
        url,
        "getBalance",
        [wallet, {"commitment": "finalized"}]
    )

    closing_slot = closing_response["context"]["slot"]

    if closing_slot < detail["slot"]:
        raise SystemExit(
            "기말 잔액 스냅샷이 거래 슬롯보다 이전입니다. "
            "finalize를 다시 시도하세요."
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
        transaction["to"] == wallet
        and transaction["status"] == "success"
    )

    # 시작 슬롯부터 이력이 보존되고 구간 서명이 예상 입금 한 건일 때만
    # coverage_complete를 True로 둔다. 부족하면 R0 UNKNOWN으로 남긴다.
    coverage = (
        first_available <= start_slot
        and len(signatures) < 1000
        and observed == {args.signature}
        and expected
    )

    data["C"]["end"] = stamp()
    data["C"]["closing"] = closing_response["value"]

    data["T"] = [transaction]

    # 현재 verify.py의 R3는 모든 T에 대응하는
    # 실행기록 L을 요구하므로 정상 입금 기록을 생성한다.
    data["L"] = [{
        "id": "execution-" + data["C"]["case_id"],
        "approval_id": None,
        "txid": args.signature,
        "result": transaction["status"],
        "time": stamp()
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
        "외부지갑에서 관리지갑으로 정상 입금한 N3 사례입니다. "
        "A/H는 사용하지 않으며, L은 입금 확인 기록입니다. "
        "coverage는 ledger 보관 범위와 관측구간 서명으로 확인합니다."
    )

    args.evidence.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )

    result = verdict(data)

    print(f"TXID {args.signature}")
    print(
        f"입금 {transaction['time']} | "
        f"slot {detail['slot']} | "
        f"{transaction['amount']} lamports"
    )
    print(
        f"기말 잔액 {closing_response['value']} lamports | "
        f"관측구간 서명 {len(in_window)}개"
    )
    print(
        f"첫 보관 블록 {first_available} | "
        f"시작 slot {start_slot} | "
        f"coverage {coverage}"
    )
    print(f"M2 verdict: {result['verdict']}")
    print(f"checks: {result['checks']}")
    print(f"saved: {args.evidence}")


def main():
    """사용자가 선택한 prepare 또는 finalize 단계만 수행한다."""
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True
    )

    start = sub.add_parser(
        "prepare",
        help="start observation before a normal deposit"
    )

    start.add_argument(
        "wallet",
        help="custody wallet public address"
    )

    start.add_argument(
        "--case-id",
        default="localnet-N3-001"
    )

    start.add_argument(
        "--rpc",
        default="http://127.0.0.1:18999"
    )

    start.add_argument(
        "--output",
        type=Path,
        default=Path(
            "research/evidence/n3-deposit.json"
        )
    )

    finish = sub.add_parser(
        "finalize",
        help="collect the deposit after manual transfer"
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
