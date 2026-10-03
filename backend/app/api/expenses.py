"""Expense endpoint."""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..common import (
    get_idempotency_key, lookup_idempotency, new_txn_no, store_idempotency, write_audit,
)
from ..models import ExpenseTransaction, Profile
from ..schemas import ExpenseCreate, TxnOut
from ..security.auth import get_current_user, get_db, require_branch_access
from ..services import accounting as acct
from ..services.costing import money

router = APIRouter(prefix="/api", tags=["expenses"])


@router.post("/expenses", status_code=status.HTTP_201_CREATED)
def create_expense(payload: ExpenseCreate, request: Request,
                   user: Profile = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    require_branch_access(payload.branch_id, user, db)
    idem_key = get_idempotency_key(request, payload.model_dump(mode="json"))
    if idem_key:
        rec = lookup_idempotency(db, idem_key, "POST /api/expenses")
        if rec:
            return JSONResponse(content=rec.response, status_code=rec.status_code)

    amount = money(payload.amount)
    txn = ExpenseTransaction(
        branch_id=payload.branch_id, txn_no=new_txn_no(db, "KK"),
        category=payload.category.strip(), description=payload.description,
        amount=amount, expense_date=payload.expense_date,
        idempotency_key=idem_key, created_by=user.id)
    db.add(txn)
    db.flush()

    acct.post_journal(
        db, branch_id=payload.branch_id, entry_date=payload.expense_date,
        lines=[(f"Beban: {txn.category}", amount, Decimal("0")),
               ("Kas", Decimal("0"), amount)],
        ref_type="expense", ref_id=txn.id, description=f"Expense {txn.txn_no}")

    write_audit(db, actor_id=user.id, branch_id=payload.branch_id,
                action="expense.create", entity_type="expense_transactions",
                entity_id=txn.id,
                after={"txn_no": txn.txn_no, "category": txn.category,
                       "amount": str(amount)})
    db.commit()

    body = TxnOut(id=txn.id, txn_no=txn.txn_no, status="posted",
                  total=amount).model_dump(mode="json")
    if idem_key:
        store_idempotency(db, key=idem_key, profile_id=user.id,
                          endpoint="POST /api/expenses",
                          response=body, status_code=201)
        db.commit()
    return JSONResponse(content=body, status_code=201)
