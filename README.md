# Hello Solana

> 논문 연구 실험: [research/README.md](research/README.md) — 압수 가상자산의 온체인 거래와 관리기록 간 정합성 검증. 이 브랜치의 기존 Counter 프로그램은 변경하지 않았습니다.

Solana 스마트 컨트랙트의 핵심 개념을 실제 코드와 트랜잭션으로 학습하기 위한 Anchor 프로젝트입니다.

현재는 `Counter` 프로그램을 통해 다음 내용을 실습합니다.

- Program과 Instruction의 관계
- Account에 상태를 저장하는 방법
- PDA(Program Derived Address)의 생성과 검증
- 트랜잭션 서명자(`Signer`) 확인
- Authority를 이용한 접근 제어
- CPI(Cross-Program Invocation)를 통한 System Program 호출
- 정상 트랜잭션과 권한 없는 공격 트랜잭션의 차이
- LiteSVM 테스트와 Localnet 실행 환경의 차이

## 현재 동작

프로그램에는 `initialize`와 `increment` 두 Instruction이 있습니다.

### `initialize`

1. `b"counter"` seed로 Counter PDA를 생성합니다.
2. `count`를 `0`으로 초기화합니다.
3. 트랜잭션의 `payer`를 Counter의 `authority`로 저장합니다.
4. System Program을 CPI로 호출하여 Counter PDA에 1 lamport를 전송합니다.

### `increment`

1. 전달된 Counter가 올바른 seed로 생성된 PDA인지 검사합니다.
2. 서명자가 Counter에 저장된 `authority`와 같은지 검사합니다.
3. `count`가 최댓값인 `10`보다 작은지 검사합니다.
4. 검사를 모두 통과하면 `count`를 1 증가시킵니다.

권한이 없는 사용자가 `increment`를 호출하면 `Unauthorized` 오류가 발생합니다. Counter가 최댓값에 도달하면 `CounterOverflow` 오류가 발생합니다.

## Account 구조

Counter PDA에는 다음 상태가 저장됩니다.

```rust
pub struct Counter {
    pub count: u64,
    pub authority: Pubkey,
}
```

- `count`: 현재 카운터 값
- `authority`: 카운터를 변경할 수 있는 지갑의 공개키

PDA 주소는 아래 두 값을 이용해 결정적으로 계산됩니다.

```text
seed: "counter"
program id: 5oWptszzLcAJhzadLLMGc6R1ghrqCqWVohsTzaEqL1wK
```

## 프로젝트 구조

```text
hello_solana/
├── Anchor.toml                         # Anchor 및 Localnet 설정
├── Cargo.toml                          # Rust workspace 설정
├── rust-toolchain.toml                 # Rust toolchain 설정
└── programs/
    └── hello_solana/
        ├── Cargo.toml                  # 프로그램 의존성
        ├── src/
        │   ├── lib.rs                  # Program 진입점과 Instruction 등록
        │   ├── constants.rs            # PDA seed와 최댓값 등 상수
        │   ├── error.rs                # 사용자 정의 오류
        │   ├── state.rs                # Counter Account 상태
        │   ├── instructions.rs         # Instruction 모듈 등록
        │   └── instructions/
        │       ├── initialize.rs       # Counter PDA 생성 및 초기화
        │       └── increment.rs        # Authority 검사 및 값 증가
        └── tests/
            ├── test_initialize.rs      # 초기화, 증가, 공격 실패 테스트
            └── test_increment.rs       # 초기화와 증가 테스트
```

## 개발 환경

- Windows + WSL2 Ubuntu
- Rust `1.89.0`
- Solana CLI
- Anchor CLI
- Solana Localnet
- LiteSVM

설치 상태는 다음 명령으로 확인할 수 있습니다.

```bash
rustc --version
solana --version
anchor --version
```

## 사용한 오픈소스

이 프로젝트는 Solana, Anchor, LiteSVM을 조합해 사용합니다. 세 도구는 같은 역할을 하는 것이 아니라 서로 다른 계층을 담당합니다.

| 오픈소스 | 이 프로젝트의 버전 | 역할 |
| --- | --- | --- |
| [Solana / Agave](https://github.com/anza-xyz/agave) | 설치된 Solana CLI 버전 사용 | Account, Transaction, Program, PDA, lamport 등이 동작하는 블록체인 플랫폼과 Localnet runtime |
| [Anchor](https://www.anchor-lang.com/docs) | `anchor-lang 1.1.2` | Rust로 Solana 프로그램을 작성·빌드·배포하기 쉽게 만드는 프레임워크 |
| [LiteSVM](https://github.com/LiteSVM/litesvm) | `litesvm 0.10.0` | Validator와 RPC 서버 없이 Solana 프로그램과 Transaction을 빠르게 테스트하는 in-process VM |

### Solana / Agave

Solana는 이 프로젝트가 실행되는 블록체인 플랫폼입니다. 프로그램 코드를 실행하고, 계정 상태를 저장하며, 서명된 Transaction을 검증합니다.

이 프로젝트에서는 다음 부분에 Solana 도구와 runtime이 사용됩니다.

- `solana-test-validator`: 내 컴퓨터에서만 동작하는 Localnet validator
- `solana` CLI: 지갑, 잔액, RPC 연결, 프로그램 정보 확인
- System Program: Account 생성과 SOL(lamport) 이동 처리
- Solana runtime: 서명, Account 권한, PDA, Transaction 실행 규칙 검증

현재 Solana validator와 CLI의 핵심 오픈소스 구현은 Anza의 **Agave** 프로젝에서 개발됩니다. 즉, 사용자 관점에서는 Solana를 사용하고, 실제 Localnet을 실행하는 소프트웨어 구현은 Agave일 수 있습니다.

### Anchor

Anchor는 Solana 위에서 스마트 컨트랙트를 작성하는 Rust 프레임워크입니다. Solana runtime을 대체하지 않고, 프로그램 개발에 필요한 반복 코드와 검증을 줄여줍니다.

이 프로젝에서는 다음 Anchor 기능을 사용합니다.

- `#[program]`: 외부에서 호출할 `initialize`, `increment` Instruction 등록
- `#[derive(Accounts)]`: Instruction에 필요한 Account 목록과 제약 정의
- `#[account]`: Solana Account에 저장할 Rust 상태 정의
- `Signer<'info>`: 트랜잭션 서명 여부 검증
- `seeds`와 `bump`: Counter PDA 주소 검증
- `require!`, `require_keys_eq!`: Authority와 카운터 조건 검증
- `anchor build`, `anchor deploy`: 프로그램 빌드와 배포

### LiteSVM

LiteSVM은 테스트 프로세스 안에서 작동하는 가벼운 Solana VM입니다. `solana-test-validator`나 `localhost:8899` RPC를 실행하지 않고도 빌드된 `.so` 프로그램을 로드해 Transaction을 실행할 수 있습니다.

현재 Rust 테스트에서 LiteSVM은 다음 일을 합니다.

1. `hello_solana.so` 프로그램을 VM에 로드합니다.
2. 테스트용 payer와 attacker `Keypair`를 만듭니다.
3. 테스트 SOL을 airdrop합니다.
4. Instruction과 Transaction을 생성하고 서명합니다.
5. Transaction을 실행한 뒤 Counter Account 상태를 읽어 결과를 검증합니다.
6. 잘못된 Authority로 보낸 공격 Transaction이 실패하는지 검증합니다.

LiteSVM은 **테스트 도구**이며 Localnet을 대체하는 배포 네트워크가 아닙니다. 빠른 자동화 테스트는 LiteSVM으로 실행하고, RPC 호출·배포·지갑 간 SOL 전송은 Localnet에서 실습합니다.

세 계층의 관계를 정리하면 다음과 같습니다.

```text
작성한 Counter 코드
        ↓ Anchor로 구조화·빌드
Solana Program (.so)
        ├─ LiteSVM에서 빠른 자동화 테스트
        └─ Solana Localnet(Agave validator)에 배포해 RPC 실습
```

세 프로젝트는 모두 Apache License 2.0으로 공개된 오픈소스입니다.

## 빌드 및 LiteSVM 테스트

프로젝트 루트에서 먼저 Solana 프로그램을 빌드합니다.

```bash
anchor build
```

그다음 Rust 테스트를 실행합니다.

```bash
cargo test
```

테스트에서는 별도의 RPC 서버를 사용하지 않습니다. LiteSVM 안에 빌드된 `hello_solana.so`를 로드하고 다음 과정을 검증합니다.

```text
Counter PDA 초기화
  → count == 0 확인
  → authority == payer 확인
  → 정상 authority의 increment 성공
  → count == 1 확인
  → 공격자의 increment 실패
  → 실패 후에도 count == 1 확인
```

## Localnet 배포

LiteSVM과 Localnet은 서로 독립된 환경입니다. Localnet에 배포하려면 먼저 별도 터미널에서 validator를 실행합니다.

```bash
solana-test-validator
```

기존 Localnet의 계정과 배포 기록을 모두 지우고 시작할 때만 다음 명령을 사용합니다.

```bash
solana-test-validator --reset
```

다른 터미널에서 CLI를 Localnet에 연결합니다.

```bash
solana config set --url localhost
solana config get
```

정상 RPC 주소는 다음과 같습니다.

```text
http://localhost:8899
```

배포 지갑의 주소와 잔액을 확인하고 필요한 경우 Localnet SOL을 받습니다.

```bash
solana address
solana balance
solana airdrop 10
```

프로그램을 빌드하고 배포합니다.

```bash
anchor build
anchor deploy
```

배포 결과를 확인합니다.

```bash
anchor keys list
solana program show 5oWptszzLcAJhzadLLMGc6R1ghrqCqWVohsTzaEqL1wK
```

`Anchor.toml`의 `skip_local_validator = true` 설정 때문에 Anchor가 validator를 자동으로 실행하지 않습니다. Localnet 테스트와 배포를 할 때는 `solana-test-validator`를 직접 실행해 두어야 합니다.

## LiteSVM과 Localnet의 차이

| 구분 | LiteSVM | Localnet |
| --- | --- | --- |
| 목적 | 빠른 프로그램 테스트 | 로컬 RPC를 통한 실제 배포와 호출 실습 |
| Validator | 필요 없음 | `solana-test-validator` 필요 |
| RPC | 사용하지 않음 | `http://localhost:8899` |
| 실행 예 | `cargo test` | `anchor deploy`, RPC 클라이언트 |
| 상태 | 테스트마다 독립적으로 구성 | validator가 실행되는 동안 유지 |

Localnet의 SOL은 실제 가치가 없지만, 공개키, 서명, Account, Program, Transaction 처리 방식은 실제 Solana와 같은 개념을 사용합니다.

## 보안상 주의할 파일

다음 정보는 절대로 Git에 커밋하지 않습니다.

- seed phrase 또는 복구 문구
- private key
- Solana keypair JSON
- API key와 기타 인증정보

학습용 Alice와 Bob 지갑을 만들더라도 keypair 파일은 프로젝트 외부(예: `~/.config/solana/`)에 보관합니다. 공개키 주소는 공유해도 되지만 keypair 파일의 숫자 배열은 공개하면 안 됩니다.

## 학습 로드맵

이 프로젝트는 Counter에서 시작해 실제 자산 이동을 다루는 작은 DeFi 실습 프로젝트로 확장하는 것을 목표로 합니다.

1. Counter: PDA, Signer, Authority
2. SOL Vault: deposit, withdraw, 권한 없는 출금 공격
3. SPL Token: mint, transfer, burn
4. Staking: deposit, withdraw, reward
5. AMM: liquidity pool, `x * y = k`, swap, slippage
6. 보안 실습: 잘못된 Account와 Authority를 이용한 공격 및 방어

각 단계에서는 성공하는 트랜잭션뿐 아니라 실패해야 하는 공격 트랜잭션도 함께 테스트합니다.
