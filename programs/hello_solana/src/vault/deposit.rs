use anchor_lang::prelude::*;
use anchor_lang::system_program::{transfer, Transfer};

use super::Vault;

#[derive(Accounts)]
pub struct Deposit<'info> {
    #[account(mut)]
    pub user: Signer<'info>,
    //sol 보내는 사람

    #[account(
        mut,
        seeds = [b"vault", user.key().as_ref()],
        bump,
        constraint = vault.authority == user.key()
    )]
    pub vault: Account<'info, Vault>,
    // sol을 받을 사람의 Vault PDA

    pub system_program: Program<'info, System>,
    // sol 전송 처리
}

pub fn handle_deposit(
    ctx: Context<Deposit>,
    amount: u64,
) -> Result<()> {
    let transfer_accounts = Transfer {
        from: ctx.accounts.user.to_account_info(),
        to: ctx.accounts.vault.to_account_info(),
    };

    let cpi_context = CpiContext::new(
        ctx.accounts.system_program.key(),
        transfer_accounts,
    );

    transfer(cpi_context, amount)?;

    msg!("Deposited {} lamports", amount);

    Ok(())
}