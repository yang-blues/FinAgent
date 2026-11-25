# -*- coding: utf-8 -*-
"""业务库同步层（仅剩初始化与探活用途）。

第二步改造后的定位
------------------
业务运行时（工具 / 图节点 / 审批路由）已全部迁到
``tools/fin_db_async.py``（SQLAlchemy AsyncSession + asyncpg），
本文件的查询与写入函数随之删除，只保留：

* ``init_db()``  —— 建表 + 灌演示数据（``tools/init_fin_db.py`` 调用）；
* 少量读函数     —— 初始化脚本最后打印验证信息用。

表结构、种子数据、合规常量的单一来源在 ``tools/fin_schema.py``，
本模块与 async 层都从那里 import。

连接串在 ``.env`` 里配一行即可::

    FINAGENT_DB_URL=postgresql+psycopg2://postgres:yang1258@127.0.0.1:5432/finagent
"""
from datetime import datetime

from untils import db_config
from untils.log_utils import log
from tools.fin_schema import _ddl, SEED_ACCOUNTS, SEED_PRODUCTS, SEED_POSITIONS

# 兼容旧引用：现在就是连接串里的库名
DB_PATH = db_config._PARAMS["database"]
DB_BACKEND = db_config.BACKEND
DB_TARGET = db_config.safe_dsn()


def cursor(conn):
    """取游标：统一用 ``RealDictCursor``，每行都是 dict，上层不用再判断类型。"""
    import psycopg2.extras
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def get_conn():
    """取当前线程的连接（thread-local，断线自动重连）。"""
    return db_config.get_conn()


def _q(sql: str, params=()):
    """执行一条 SQL 并返回游标（读操作）。"""
    cur = cursor(get_conn())
    cur.execute(sql, params)
    return cur


_initialized = False


def init_db(force=False):
    """建表并灌入演示数据。

    参数:
        force (bool): True 时清空业务表重建（审计日志保留，审计不该被清）。

    建表只做一次（模块级 ``_initialized``）：每条查询前跑一遍
    ``CREATE TABLE IF NOT EXISTS`` 是白白多一次网络往返。
    """
    global _initialized
    if _initialized and not force:
        return
    conn = get_conn()
    cur = cursor(conn)
    for stmt in _ddl():
        cur.execute(stmt)
    conn.commit()

    if force:
        for t in ("orders", "positions", "products", "accounts",
                  "compliance_ticket"):
            cur.execute(f"DELETE FROM {t}")
        conn.commit()

    cur.execute("SELECT COUNT(*) AS c FROM products")
    row = cur.fetchone()
    count = row["c"] if isinstance(row, dict) else row[0]
    if count == 0:
        cur.executemany(db_config.insert_ignore(
            "accounts", "user_id,name,risk_level,cash,status", "%s,%s,%s,%s,%s"),
            [a + ("active",) for a in SEED_ACCOUNTS])
        cur.executemany(db_config.insert_ignore(
            "products",
            "product_code,name,risk_level,nav,category,min_buy,status",
            "%s,%s,%s,%s,%s,%s,%s"),
            [p + ("on_sale",) for p in SEED_PRODUCTS])
        cur.executemany(
            "INSERT INTO positions(user_id,product_code,shares,cost)"
            " VALUES (%s,%s,%s,%s)", SEED_POSITIONS)
        conn.commit()
        log.info(f"业务库初始化完成: {DB_TARGET}")
    _initialized = True


# ------------------------------------------------------------------ 查询（初始化脚本验证用）
def get_account(user_id: str):
    """查账户（含风险等级与可用资金）。"""
    init_db()
    row = _q("SELECT * FROM accounts WHERE user_id = %s", (user_id,)).fetchone()
    return dict(row) if row else None


def list_products():
    """列出在售产品。"""
    init_db()
    rows = _q("SELECT * FROM products WHERE status = 'on_sale'").fetchall()
    return [dict(r) for r in rows]


def get_positions(user_id: str):
    """查持仓，带产品名称与当前市值。"""
    init_db()
    rows = _q(
        """
        SELECT p.product_code, pr.name, pr.nav, pr.risk_level, p.shares, p.cost
        FROM positions p JOIN products pr ON pr.product_code = p.product_code
        WHERE p.user_id = %s
        """, (user_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["market_value"] = round(float(d["shares"]) * float(d["nav"]), 2)
        out.append(d)
    return out


def get_total_asset(user_id: str) -> float:
    """账户总资产 = 现金 + 持仓市值。"""
    acc = get_account(user_id) or {}
    mv = sum(p["market_value"] for p in get_positions(user_id))
    return float(acc.get("cash", 0.0)) + mv


if __name__ == "__main__":
    init_db(force=False)
    print(f"后端 = {DB_BACKEND} | 目标 = {DB_TARGET}")
    print("账户:", get_account("u_1002"))
    print("总资产:", get_total_asset("u_1002"))
