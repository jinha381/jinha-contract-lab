use anchor_lang::prelude::*;

pub mod initialize_vault;
pub mod deposit;

pub use initialize_vault::*;
pub use deposit::*;


#[account]
#[derive(InitSpace)]
pub struct Vault {
    pub authority: Pubkey,
}