use anchor_lang::prelude::*;

use super::Vault;

#[derive(Accounts)]
pub struct InitializeVault<'info> {
    #[account(mut)]
    pub payer: Signer<'info>,

    #[account(
        init,
        payer = payer,
        space = 8 + Vault::INIT_SPACE,
        seeds = [b"vault", payer.key().as_ref()],
        // 사용자들이 각각의 Vault PDA를 갖게 함
        bump
    )]
    pub vault: Account<'info, Vault>,

    pub system_program: Program<'info, System>,
}

pub fn handle_initialize_vault(
    ctx: Context<InitializeVault>
) -> Result<()> {
    ctx.accounts.vault.authority = ctx.accounts.payer.key();

    Ok(())
}