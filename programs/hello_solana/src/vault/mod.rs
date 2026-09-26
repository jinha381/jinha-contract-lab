use anchor_lang::prelude::*;

pub mod initialize_vault;

pub use initialize_vault::*;

#[account]
#[derive(InitSpace)]
pub struct Vault {
    pub authority: Pubkey,
}