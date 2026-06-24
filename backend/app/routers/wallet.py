from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.auth.dependencies import current_active_user

router = APIRouter()


@router.get("")
async def get_wallet(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Wallet).where(Wallet.user_id == user.id)
    )
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    txn_result = await session.execute(
        select(WalletTransaction)
        .where(WalletTransaction.user_id == user.id)
        .order_by(WalletTransaction.created_at.desc())
        .limit(50)
    )
    transactions = txn_result.scalars().all()

    return {
        "balance_paise": wallet.balance_paise,
        "transactions": [
            {
                "id": str(t.id),
                "description": t.description,
                "amount_paise": t.amount_paise,
                "balance_after_paise": t.balance_after_paise,
                "transaction_type": t.transaction_type,
                "created_at": t.created_at,
            }
            for t in transactions
        ]
    }
