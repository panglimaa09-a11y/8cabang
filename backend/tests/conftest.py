"""Shared fixtures: in-memory SQLite + seeded reference data.

No live Postgres needed. The models' GUID TypeDecorator emulates UUID on
SQLite so the same ORM code runs in tests and production.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Base, Branch, BranchMembership, Product, Profile, RolePermission,
)


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    maker = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, future=True)
    session = maker()
    yield session
    session.close()


@pytest.fixture()
def seed(db):
    """Branches C1/C2, 4 products, role permissions, one user per role."""
    branches = {}
    for code, name in (("C1", "Cabang 1"), ("C2", "Cabang 2")):
        b = Branch(code=code, name=name)
        db.add(b)
        branches[code] = b
    products = {}
    for sku, name in (("TL-AYAM-RAS", "Telur Ayam Ras"),
                      ("TL-AYAM-KAMPUNG", "Telur Ayam Kampung"),
                      ("TL-BEBEK", "Telur Bebek"),
                      ("TL-PUYUH", "Telur Puyuh")):
        p = Product(sku=sku, name=name, base_unit="butir",
                    units={"butir": 1, "rak": 30, "peti": 180, "kg": 16})
        db.add(p)
        products[sku] = p
    for role, key in (("owner", "reports.view_profit"), ("owner", "reports.view_margin"),
                      ("owner", "inventory.view_cost"), ("owner", "transactions.correct"),
                      ("owner", "users.manage"), ("owner", "audit.view"),
                      ("owner", "branches.manage"), ("owner", "settings.manage"),
                      ("admin", "audit.view")):
        db.add(RolePermission(role=role, permission_key=key))

    users = {}
    specs = [("owner", "owner@x.id", ["C1", "C2"]),
             ("admin", "admin@x.id", ["C1"]),
             ("karyawan", "staff@x.id", ["C1"])]
    for role, email, bcodes in specs:
        u = Profile(email=email, full_name=role.title(), role=role,
                    password_hash="hashed")
        db.add(u)
        db.flush()
        for bc in bcodes:
            db.add(BranchMembership(profile_id=u.id, branch_id=branches[bc].id))
        users[role] = u
    db.commit()
    return {"branches": branches, "products": products, "users": users}


def uid() -> uuid.UUID:
    return uuid.uuid4()


def dec(v) -> Decimal:
    return Decimal(str(v))
