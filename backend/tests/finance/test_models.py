import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.memory.models import Account, PlaidItem, Transaction


async def test_item_account_transaction_persist(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as s:
        item = PlaidItem(institution_name="Chase", access_token="enc", item_id="it_1")
        s.add(item)
        await s.flush()
        acct = Account(
            item_id=item.id,
            plaid_account_id="ac_1",
            name="Checking",
            type="depository",
            current_balance=Decimal("100.50"),
        )
        s.add(acct)
        await s.flush()
        s.add(
            Transaction(
                account_id=acct.id,
                plaid_txn_id="tx_1",
                date=dt.date(2026, 6, 20),
                name="Coffee",
                amount=Decimal("4.25"),
                pending=False,
            )
        )
        await s.commit()

    async with session_factory() as s:
        txns = list((await s.execute(select(Transaction))).scalars().all())
        assert txns[0].name == "Coffee" and txns[0].amount == Decimal("4.25")
