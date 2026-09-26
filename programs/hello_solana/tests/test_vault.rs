use {
    anchor_lang::{
        prelude::Pubkey,
        solana_program::{instruction::Instruction, system_program},
        AccountDeserialize, InstructionData, ToAccountMetas,
    },
    litesvm::LiteSVM,
    solana_message::{Message, VersionedMessage},
    solana_keypair::Keypair,
    solana_signer::Signer,
    solana_transaction::versioned::VersionedTransaction,
};

#[test]
fn test_vault_deposit() {
    // 우리가 만든 hello_solana 프로그램의 주소
    let program_id = hello_solana::id();

    // Vault를 사용할 Alice 생성
    let alice = Keypair::new();

    // Alice 전용 Vault PDA 계산
    let (vault, _bump) = Pubkey::find_program_address(
        &[b"vault", alice.pubkey().as_ref()],
        &program_id,
    );

    // 테스트용 Solana 환경 생성
    let mut svm = LiteSVM::new();

    // Alice에게 테스트용 10 SOL 지급
    svm.airdrop(
        &alice.pubkey(),
        10_000_000_000,
    )
    .unwrap();

    println!("Alice: {}", alice.pubkey());
    println!("Alice Vault PDA: {}", vault);

    // 우리가 빌드한 hello_solana 프로그램을 LiteSVM에 등록
    let bytes = include_bytes!(concat!(
    env!("CARGO_TARGET_TMPDIR"),
    "/../deploy/hello_solana.so"
    ));

    svm.add_program(program_id, bytes).unwrap();
    

    //initialize_vault 명령어 만들기
    let instruction = Instruction::new_with_bytes(
        program_id,

        &hello_solana::instruction::InitializeVault {}.data(),

        hello_solana::accounts::InitializeVault {
        payer: alice.pubkey(),
        vault,
        system_program: system_program::ID,
    }
        .to_account_metas(None),
    );

    // 트랜잭션 만들어서 앨리스가 서명

    let blockhash = svm.latest_blockhash();

    let msg = Message::new_with_blockhash(
        &[instruction],
        Some(&alice.pubkey()),
        &blockhash,
     );

    let tx = VersionedTransaction::try_new(
        VersionedMessage::Legacy(msg),
        &[&alice],
     )
     .unwrap();

    //전송
    let res = svm.send_transaction(tx);

    assert!(res.is_ok());

    // 앨리스 권한 검증
    let vault_account = svm.get_account(&vault).unwrap();

    let mut data: &[u8] = &vault_account.data;

    let vault_state =
        hello_solana::vault::Vault::try_deserialize(&mut data).unwrap();

    assert_eq!(vault_state.authority, alice.pubkey());}