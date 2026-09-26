pub mod constants;
pub mod error;
pub mod instructions;
pub mod state;
// Vault 알리기
pub mod vault;

use anchor_lang::prelude::*;

pub use constants::*;
pub use instructions::*;
pub use state::*;
pub use vault::*;

declare_id!("5oWptszzLcAJhzadLLMGc6R1ghrqCqWVohsTzaEqL1wK");

#[program]
pub mod hello_solana {
    use super::*;

    pub fn initialize(ctx: Context<Initialize>) -> Result<()> {
        crate::instructions::initialize::handle_initialize(ctx)
    }

    pub fn increment(ctx: Context<Increment>) -> Result<()> {
        crate::instructions::increment::handle_increment(ctx)
    }

    pub fn initialize_vault(ctx: Context<InitializeVault>) -> Result<()> {
    crate::vault::initialize_vault::handle_initialize_vault(ctx)
    }

    pub fn deposit(ctx: Context<Deposit>, amount: u64,) -> Result<()> {
    crate::vault::deposit::handle_deposit(ctx, amount)
    }

}
