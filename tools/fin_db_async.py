# -*- coding: utf-8 -*-
"""业务库异步数据层：账户 / 产品 / 持仓 / 订单 / 审计 / 合规票据。

与同步层（``tools/fin_db.py``）的关系
--------------------------------------
* 函数一一对应，业务语义与返回结构完全相同，只是全部变成 async；
* DDL、种子数据、合规常量（RISK_CEILING / DAILY_LIMIT 等）在
  ``tools/fin_schema.py`` 统一定义，同步初始化层与本层共享单一来源；
* 第二步改造后本文件是**业务运行时的唯一数据层**（工具 / 图节点 /
  审批路由全部走这里），同步层 ``fin_db.py`` 只剩初始化脚本在用。

SQL 翻译规则（psycopg2 → asyncpg）
----------------------------------
* 占位符 ``%s`` → ``:name``（SQLAlchemy ``text()`` 命名参数）；
* ``RETURNING`` 语义不变，用 ``session.execute(...).scalar_one()`` 取回；
* 唯一约束冲突由 SQLAlchemy 包装成 ``IntegrityError``，
  ``INTEGRITY_ERRORS`` 与同步层同名导出，上层 catch 代码不变。

事务约定
--------
* 读操作走自动 begin/rollback 的隐式事务（只读无副作用）；
* 写操作统一 ``async with session.begin():`` 块，块尾自动 commit，
  异常自动 rollback——与同步层"手动 commit"语义等价。
"""
import json
import secrets
from datetime import datetime

from sqlalchemy import text

from tools.fin_schema import (CONCENTRATION_LIMIT, DAILY_LIMIT, RISK_CEILING,
                              SEED_ACCOUNTS, SEED_POSITIONS, SEED_PRODUCTS,
                              _as_text, _ddl)
from untils.async_db import INTEGRITY_ERRORS, AsyncSessionLocal
from untils.log_utils import log

# re-export：上层（工具/节点）只 import 本模块即可拿到全部常量
__all__ = [
    "INTEGRITY_ERRORS", "RISK_CEILING", "DAILY_LIMIT", "CONCENTRATION_LIMIT",
    "init_db", "get_account", "get_product", "list_products", "get_positions",
    "get_today_buy_amount", "get_total_asset", "place_order_row",
    "update_order_status", "deduct_cash", "find_order_by_client_id",
    "list_orders", "write_audit", "issue_ticket_row", "consume_ticket",
    "revoke_tickets", "get_ticket", "get_pending_ticket",
]

_initialized = False


# ------------------------------------------------------------------ 初始化
async def init_db(force: bool = False):
    """建表并灌入演示数据（幂等，进程内只跑一次；语义同同步层）。"""
    global _initialized
    if _initialized and not force:
        return
    async with AsyncSessionLocal() as s, s.begin():
        for stmt in _ddl():
            await s.execute(text(stmt))
        if force:
            for t in ("orders", "positions", "products", "accounts",
                      "compliance_ticket"):
                await s.execute(text(f"DELETE FROM {t}"))
        row = await s.execute(text("SELECT COUNT(*) AS c FROM products"))
        count = row.scalar_one()
    if count == 0:
        async with AsyncSessionLocal() as s, s.begin():
            await s.execute(text(
                "INSERT INTO accounts(user_id,name,risk_level,cash,status)"
                " VALUES (:uid,:name,:risk,:cash,'active')"
                " ON CONFLICT DO NOTHING"),
                [{"uid": a[0], "name": a[1], "risk": a[2], "cash": a[3]}
                 for a in SEED_ACCOUNTS])
            await s.execute(text(
                "INSERT INTO products(product_code,name,risk_level,nav,"
                "category,min_buy,status)"
                " VALUES (:code,:name,:risk,:nav,:cat,:min_buy,'on_sale')"
                " ON CONFLICT DO NOTHING"),
                [{"code": p[0], "name": p[1], "risk": p[2], "nav": p[3],
                  "cat": p[4], "min_buy": p[5]} for p in SEED_PRODUCTS])
            await s.execute(text(
                "INSERT INTO positions(user_id,product_code,shares,cost)"
                " VALUES (:uid,:code,:shares,:cost)"),
                [{"uid": r[0], "code": r[1], "shares": r[2], "cost": r[3]}
                 for r in SEED_POSITIONS])
        log.info("业务库初始化完成（async 层）")
    _initialized = True


# ------------------------------------------------------------------ 查询
async def get_account(user_id: str) -> dict | None:
    """查账户（含风险等级与可用资金）。"""
    await init_db()
    async with AsyncSessionLocal() as s:
        rows = await s.execute(text(
            "SELECT * FROM accounts WHERE user_id = :uid"), {"uid": user_id})
        row = rows.mappings().first()
        return dict(row) if row else None


async def get_product(product_code: str) -> dict | None:
    """查单个产品要素，None 表示不存在（→ insufficient_evidence）。"""
    await init_db()
    async with AsyncSessionLocal() as s:
        rows = await s.execute(text(
            "SELECT * FROM products WHERE product_code = :code"),
            {"code": product_code})
        row = rows.mappings().first()
        return dict(row) if row else None


async def list_products() -> list[dict]:
    """列出在售产品。"""
    await init_db()
    async with AsyncSessionLocal() as s:
        rows = await s.execute(text(
            "SELECT * FROM products WHERE status = 'on_sale'"))
        return [dict(r) for r in rows.mappings().all()]


async def get_positions(user_id: str) -> list[dict]:
    """查持仓，带产品名称与当前市值（市值在 Python 算，同同步层）。"""
    await init_db()
    async with AsyncSessionLocal() as s:
        rows = await s.execute(text(
            "SELECT p.product_code, pr.name, pr.nav, pr.risk_level,"
            " p.shares, p.cost"
            " FROM positions p JOIN products pr"
            " ON pr.product_code = p.product_code"
            " WHERE p.user_id = :uid"), {"uid": user_id})
        out = []
        for r in rows.mappings().all():
            d = dict(r)
            d["market_value"] = round(float(d["shares"]) * float(d["nav"]), 2)
            out.append(d)
        return out


async def get_today_buy_amount(user_id: str) -> float:
    """当日已申购金额，用于限额校验。"""
    await init_db()
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as s:
        rows = await s.execute(text(
            "SELECT COALESCE(SUM(amount),0) AS s FROM orders"
            " WHERE user_id = :uid AND action = 'buy' AND status != 'rejected'"
            " AND substr(created_at,1,10) = :today"),
            {"uid": user_id, "today": today})
        return float(rows.scalar_one())


async def get_total_asset(user_id: str) -> float:
    """账户总资产 = 现金 + 持仓市值。"""
    acc = await get_account(user_id) or {}
    mv = sum(p["market_value"] for p in await get_positions(user_id))
    return float(acc.get("cash", 0.0)) + mv


# ------------------------------------------------------------------ 写入
async def place_order_row(user_id, product_code, action, amount,
                          client_order_id, snapshot) -> int:
    """落订单并返回自增 ID（client_order_id 唯一约束兜底幂等）。"""
    await init_db()
    async with AsyncSessionLocal() as s, s.begin():
        row = await s.execute(text(
            "INSERT INTO orders(user_id,product_code,action,amount,status,"
            "client_order_id,decision_snapshot,created_at)"
            " VALUES (:uid,:code,:action,:amount,'pending',:cid,:snapshot,:ts)"
            " RETURNING order_id"),
            {"uid": user_id, "code": product_code, "action": action,
             "amount": float(amount), "cid": client_order_id,
             "snapshot": _as_text(snapshot),
             "ts": datetime.now().isoformat(timespec="seconds")})
        return int(row.scalar_one())


async def update_order_status(order_id: int, status: str):
    """更新订单状态。"""
    async with AsyncSessionLocal() as s, s.begin():
        await s.execute(text(
            "UPDATE orders SET status = :st WHERE order_id = :oid"),
            {"st": status, "oid": order_id})


async def deduct_cash(user_id: str, amount: float):
    """扣减可用资金（买入成交时）。"""
    async with AsyncSessionLocal() as s, s.begin():
        await s.execute(text(
            "UPDATE accounts SET cash = cash - :amt WHERE user_id = :uid"),
            {"amt": float(amount), "uid": user_id})


async def find_order_by_client_id(client_order_id: str) -> dict | None:
    """按幂等键查单，重复提交时返回同一张单而不是新建。"""
    await init_db()
    async with AsyncSessionLocal() as s:
        rows = await s.execute(text(
            "SELECT * FROM orders WHERE client_order_id = :cid"),
            {"cid": client_order_id})
        row = rows.mappings().first()
        return dict(row) if row else None


async def list_orders(user_id: str, limit: int = 20) -> list[dict]:
    """查历史订单（LIMIT 在 Python 切，省一次往返，同同步层）。"""
    await init_db()
    async with AsyncSessionLocal() as s:
        rows = await s.execute(text(
            "SELECT * FROM orders WHERE user_id = :uid"
            " ORDER BY order_id DESC"), {"uid": user_id})
        return [dict(r) for r in rows.mappings().all()[:int(limit)]]


async def write_audit(user_id, action, payload, result, evidence=""):
    """审计日志：谁发起、做了什么、依据是什么、结果如何。"""
    await init_db()
    async with AsyncSessionLocal() as s, s.begin():
        await s.execute(text(
            "INSERT INTO audit_log(ts,user_id,action,payload,result,evidence)"
            " VALUES (:ts,:uid,:action,:payload,:result,:evidence)"),
            {"ts": datetime.now().isoformat(timespec="seconds"),
             "uid": user_id, "action": action, "payload": _as_text(payload),
             "result": str(result), "evidence": _as_text(evidence)})


# ------------------------------------------------------------------ 合规票据
def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


async def issue_ticket_row(thread_id, user_id, action, product_code, amount,
                           evidence_hash="", tool_call_id="", client_order_id="",
                           ttl=300) -> str:
    """签发票据并落库，返回 ticket_id（只有合规 pass 才会走到这里）。"""
    await init_db()
    issued = _now_text()
    expires = datetime.fromtimestamp(
        datetime.now().timestamp() + ttl).isoformat(timespec="seconds")
    ticket_id = secrets.token_hex(12)
    async with AsyncSessionLocal() as s, s.begin():
        await s.execute(text(
            "INSERT INTO compliance_ticket(ticket_id,thread_id,user_id,action,"
            "product_code,amount,decision,evidence_hash,status,issued_at,"
            "expires_at,tool_call_id,client_order_id)"
            " VALUES (:tid,:thid,:uid,:action,:code,:amount,'pass',:eh,"
            "'issued',:issued,:expires,:tcid,:cid)"),
            {"tid": ticket_id, "thid": thread_id, "uid": user_id,
             "action": action, "code": str(product_code or ""),
             "amount": float(amount or 0), "eh": evidence_hash,
             "issued": issued, "expires": expires,
             "tcid": tool_call_id, "cid": client_order_id})
    log.info(f"签发合规票据 {ticket_id} | {action} {product_code} {amount}")
    return ticket_id


async def consume_ticket(thread_id, action, product_code=None, amount=None,
                         tolerance=1.0) -> dict | None:
    """原子核销：一条 UPDATE ... RETURNING 同时完成"校验"与"作废"。

    WHERE 里的 status='issued' 由数据库行锁保证并发下只有一个请求
    能 RETURNING 到行——重放攻击与重复提交都卡在这里（fail-closed）。
    """
    await init_db()
    now = _now_text()
    sql = ("UPDATE compliance_ticket SET status='consumed', consumed_at=:now"
           " WHERE thread_id=:thid AND status='issued' AND expires_at > :now"
           " AND action=:action")
    params = {"now": now, "thid": thread_id, "action": action}
    if product_code is not None:
        sql += " AND product_code = :code"
        params["code"] = str(product_code)
    if amount is not None:
        sql += " AND (amount = 0 OR ABS(amount - :amt) <= :tol)"
        params["amt"] = float(amount)
        params["tol"] = float(tolerance)
    sql += (" RETURNING ticket_id,user_id,action,product_code,amount,"
            "evidence_hash,issued_at")
    async with AsyncSessionLocal() as s, s.begin():
        rows = await s.execute(text(sql), params)
        row = rows.mappings().first()
        return dict(row) if row else None


async def revoke_tickets(thread_id) -> int:
    """吊销该会话所有未核销票据，返回吊销张数。"""
    await init_db()
    async with AsyncSessionLocal() as s, s.begin():
        rows = await s.execute(text(
            "UPDATE compliance_ticket SET status='revoked'"
            " WHERE thread_id=:thid AND status='issued'"),
            {"thid": thread_id})
        return int(rows.rowcount or 0)


async def get_ticket(ticket_id: str) -> dict | None:
    """按票据号查（审批卡片与审计追溯用）。"""
    await init_db()
    async with AsyncSessionLocal() as s:
        rows = await s.execute(text(
            "SELECT * FROM compliance_ticket WHERE ticket_id = :tid"),
            {"tid": ticket_id})
        row = rows.mappings().first()
        return dict(row) if row else None


async def get_pending_ticket(thread_id: str) -> dict | None:
    """取该会话最新一张未核销票据。"""
    await init_db()
    async with AsyncSessionLocal() as s:
        rows = await s.execute(text(
            "SELECT * FROM compliance_ticket"
            " WHERE thread_id = :thid AND status = 'issued'"
            " ORDER BY issued_at DESC"), {"thid": thread_id})
        row = rows.mappings().first()
        return dict(row) if row else None


if __name__ == "__main__":
    import asyncio

    async def _smoke():
        await init_db()
        print("账户 u_1002:", await get_account("u_1002"))
        print("持仓 u_1002:", await get_positions("u_1002"))
        print("总资产 u_1002:", await get_total_asset("u_1002"))
        print("在售产品数:", len(await list_products()))

    asyncio.run(_smoke())
