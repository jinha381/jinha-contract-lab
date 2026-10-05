# 압수 가상자산 관리기록 정합성 실험

대상 초안: `26동계 진하 v0.2.pdf`, 「압수 가상자산의 온체인 거래와 관리기록 간 불일치 탐지를 위한 규칙 기반 상호 검증 모델」. 이 브랜치는 Python 표준 라이브러리 기반 실험 환경입니다. PDF 자체와 지갑 비밀키는 저장소에 넣지 않습니다.

## 빠른 실행

Windows PowerShell 또는 WSL에서 Python 3.10 이상을 사용합니다.

```bash
cd hello_solana
python research/run_experiments.py
```

첫 명령은 N1~N3, X1~X6, U1~U3의 합성 입력을 생성하여 M1/M2 판정을 비교하고 `research/results.json`을 씁니다. 개별 증거 JSON 검증은 아래의 Localnet 절차에서 수집한 파일로 실행합니다. 금액은 모두 lamport 정수이며 시각은 UTC ISO 8601 문자열입니다.

입력 형식은 [정상 출금 예시](examples/approved-withdrawal.json)로 확인할 수 있습니다. `python research/verify.py research/examples/approved-withdrawal.json`은 `PASS`를 반환합니다. 예시의 주소와 TXID는 실제 체인 값이 아닙니다.

## 데이터와 판정

| 기호 | JSON 필드 | 내용 |
| --- | --- | --- |
| C | `C` | 사건, 관리지갑, SOL, 관측 시작/끝, 기초/기말 잔액 |
| A | `A` | 승인 ID, 금액, 수신자, 유효기간, 허용 사용횟수 |
| H | `H` | 승인 상태와 변경 시각 |
| L | `L` | 실행기록과 TXID, 승인 ID, 결과 |
| T | `T` | 확인된 거래의 TXID, 송수신자, 금액, 시각, 상태, 수수료 |

M1은 승인 존재·금액·수신주소만 비교합니다. M2는 R0 자료 충족, R1 범위, R2 승인 조건과 이력·재사용, R3 실행기록 대응, R4 잔액 흐름을 검사합니다. R0가 미충족이면 `UNKNOWN`; 자료가 충분하고 명확한 차이가 있으면 `FAIL`; 모든 규칙을 충족하면 `PASS`입니다. `results.json`의 합성 결과는 논문 실험 결과로 간주하지 않습니다.

## Solana Localnet 실험

네이티브 SOL 단순 이전에는 별도 온체인 프로그램이 필요하지 않습니다. WSL2에서 Solana CLI가 설치돼 있다면 별도 터미널에 validator를 실행하고 테스트용 지갑만 사용합니다.

```bash
solana-test-validator
solana config set --url localhost
solana-keygen new --outfile /tmp/custody.json --no-bip39-passphrase
solana-keygen new --outfile /tmp/recipient.json --no-bip39-passphrase
CUSTODY=$(solana-keygen pubkey /tmp/custody.json)
RECIPIENT=$(solana-keygen pubkey /tmp/recipient.json)
solana airdrop 2 "$CUSTODY"
solana balance --lamports "$CUSTODY" # 관측 시작 잔액을 기록
solana transfer "$RECIPIENT" 0.1 --from /tmp/custody.json --allow-unfunded-recipient
solana balance --lamports "$CUSTODY" # 관측 종료 잔액을 기록
```

PowerShell에서 같은 PC의 Localnet RPC와 연결된다면 다음처럼 거래를 수집합니다. WSL만 RPC에 접근할 수 있는 구성이라면 WSL 안에서 명령을 실행합니다.

```bash
python research/capture_localnet.py <custody-public-address>
```

`research/localnet-evidence.json`에서 `C.case_id`, 관측 `start/end`, 거래 이전/이후의 `opening/closing` 잔액을 입력하고 실험에 맞는 `A/H/L` 기록을 채웁니다. 관측 시작은 airdrop 이후, transfer 이전으로 잡습니다. 수집된 TXID와 CLI 거래 결과, RPC 조회 범위, 누락된 서명 및 내부 instruction을 직접 확인한 뒤에만 `coverage_complete`를 `true`로 바꿉니다. 수집기는 단일 top-level System Program transfer만 추출합니다. 다른 거래가 관측범위 안에 있거나 누락이 있으면 `UNKNOWN`으로 유지해야 합니다. `getSignaturesForAddress`의 `--limit`가 결과를 자르면 추가 수집이 필요합니다.

```bash
python research/verify.py research/localnet-evidence.json
python research/verify.py research/localnet-evidence.json --baseline
python research/verify.py research/localnet-evidence.json --omit H
python research/verify.py research/localnet-evidence.json --omit use_limit
python research/verify.py research/localnet-evidence.json --omit R3
```

`--omit`는 A1~A3 정보·규칙 제거 실험입니다. A4는 `L.approval_id` 연결을 제거하고 복수의 승인 후보를 제공하여 `UNKNOWN` 발생을 확인합니다. A5a/A5b는 U1~U3 결과를 각각 PASS/FAIL로 강제했을 때의 오단정 수를 `results.json`에서 별도로 집계합니다. 승인 이력이나 RPC 기록의 진실성은 이 검증기가 증명하지 않습니다.

## 논문 결과표 작성

`results.json`의 `cases`를 Table 11의 M1/M2 판정에, 기대판정과의 교차 집계를 Table 12에 사용합니다. 각 시나리오를 주소·금액·거래 순서를 바꿔 반복하고 Localnet에서 얻은 원본 TXID, 실행 시각, 지갑 주소, CLI/RPC 버전, 관측범위 및 누락 여부를 별도 실험 일지에 남기세요. 합성 사례와 Localnet 실측 사례를 표에서 구분해야 합니다. 현재 구현은 실제 기관 기록이나 메인넷 상태를 검증하지 않습니다.
