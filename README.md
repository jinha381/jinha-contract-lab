# 온체인 거래와 관리기록 정합성 검증 실험

「압수 가상자산의 온체인 거래와 관리기록 간 불일치 탐지를 위한 규칙 기반 상호 검증 모델」 연구용 실험 저장소입니다. Solana Localnet의 네이티브 SOL 이전 거래와 합성 관리기록을 사용합니다.

## 시작하기

Python 3.10 이상이 필요합니다. 합성 시나리오 12개와 제거 실험을 실행합니다.

```bash
python research/run_experiments.py
```

판정 결과는 `research/results.json`에 생성됩니다. Localnet 거래 수집, 증거 JSON 작성, M1/M2 비교 및 실험 한계는 [실험 안내](research/README.md)를 참고하세요.

## 로컬 대시보드

Localnet이 실행 중일 때 다음 명령을 실행한 뒤 브라우저에서 `http://127.0.0.1:8765`를 엽니다.

```bash
python dashboard/server.py --rpc http://127.0.0.1:18999
```

대시보드는 거래 전송 기능 없이 RPC의 슬롯·잔액·주소별 최근 거래와 `research/examples/*.json`, `research/evidence/*.json`의 증거·M1/M2·R0~R4 판정 결과를 보여줍니다. 기본 RPC 주소는 현재 연구용 Localnet의 `18999` 포트입니다. 다른 포트를 쓰면 `--rpc`를 바꾸세요. 웹 서버는 PC의 `127.0.0.1:8765`에만 열립니다. 종료는 실행 터미널에서 `Ctrl+C`입니다.
