
use {
    anchor_lang::{
        prelude::Pubkey,
        solana_program::{instruction::Instruction, system_program},
        AccountDeserialize, InstructionData, ToAccountMetas,
    },
    litesvm::LiteSVM,
    solana_keypair::Keypair,
    solana_message::{Message, VersionedMessage},
    solana_signer::Signer,
    solana_transaction::versioned::VersionedTransaction,
};

#[test]
fn test_initialize_and_increment() {
    let program_id = hello_solana::id();
    let payer = Keypair::new();
    let attacker = Keypair::new();
    
    let counter = Pubkey::find_program_address(
        &[hello_solana::constants::COUNTER_SEED],
        &program_id,
    )
    .0;
    let mut svm = LiteSVM::new();
    let bytes = include_bytes!(concat!(
        env!("CARGO_TARGET_TMPDIR"),
        "/../deploy/hello_solana.so"
    ));
    svm.add_program(program_id, bytes).unwrap();
    svm.airdrop(&payer.pubkey(), 1_000_000_000).unwrap();
    svm.airdrop(&attacker.pubkey(), 1_000_000_000).unwrap();

    let instruction = Instruction::new_with_bytes(
        program_id,
        &hello_solana::instruction::Initialize {}.data(),
        hello_solana::accounts::Initialize {
            payer: payer.pubkey(),
            counter,
            system_program: system_program::ID,
        }
        .to_account_metas(None),
    );

    let blockhash = svm.latest_blockhash();
    let msg = Message::new_with_blockhash(&[instruction], Some(&payer.pubkey()), &blockhash);
    let tx = VersionedTransaction::try_new(VersionedMessage::Legacy(msg), &[&payer]).unwrap();

    let res = svm.send_transaction(tx);
    assert!(res.is_ok());

    let counter_account = svm.get_account(&counter).unwrap();
    let mut data: &[u8] = &counter_account.data;
    let counter_state = hello_solana::state::Counter::try_deserialize(&mut data).unwrap();
    assert_eq!(counter_state.count, 0);
    assert_eq!(counter_state.authority, payer.pubkey());

    let instruction = Instruction::new_with_bytes(
        program_id,
        &hello_solana::instruction::Increment {}.data(),
        hello_solana::accounts::Increment {
            counter,
            authority: payer.pubkey(),
        }
        .to_account_metas(None),
    );

    let blockhash = svm.latest_blockhash();
    let msg = Message::new_with_blockhash(&[instruction], Some(&payer.pubkey()), &blockhash);
    let tx = VersionedTransaction::try_new(VersionedMessage::Legacy(msg), &[&payer]).unwrap();

    let res = svm.send_transaction(tx);
    assert!(res.is_ok());

    let counter_account = svm.get_account(&counter).unwrap();
    let mut data: &[u8] = &counter_account.data;
    let counter_state = hello_solana::state::Counter::try_deserialize(&mut data).unwrap();
    assert_eq!(counter_state.count, 1);
    assert_eq!(counter_state.authority, payer.pubkey());
    // Bob(attacker)이 Alice의 Counter를 증가시키려고 시도
    let instruction = Instruction::new_with_bytes(
    program_id,
    &hello_solana::instruction::Increment {}.data(),
    hello_solana::accounts::Increment {
        counter,
        authority: attacker.pubkey(),
    }
    .to_account_metas(None),
);

let blockhash = svm.latest_blockhash();

let msg = Message::new_with_blockhash(
    &[instruction],
    Some(&attacker.pubkey()),
    &blockhash,
);

let tx = VersionedTransaction::try_new(
    VersionedMessage::Legacy(msg),
    &[&attacker],
)
.unwrap();

let res = svm.send_transaction(tx);

// 기존 assert!(res.is_err());
// 취약한 프로그램에서는 Bob의 공격이 성공
assert!(res.is_ok());

// 실험1 : 실패했으므로 count는 여전히 1이어야 함
let counter_account = svm.get_account(&counter).unwrap();
let mut data: &[u8] = &counter_account.data;

let counter_state =
    hello_solana::state::Counter::try_deserialize(&mut data).unwrap();

// 기존 assert_eq!(counter_state.count, 1);
assert_eq!(counter_state.count, 2);
// Counter의 주인은 여전히 Alice
assert_eq!(counter_state.authority, payer.pubkey());
}
