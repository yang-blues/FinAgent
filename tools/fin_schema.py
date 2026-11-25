# -*- coding: utf-8 -*-
"""业务库表结构与合规常量的单一来源。

第二步改造后同步数据层（``fin_db.py``）只剩初始化脚本在用，
业务运行时全部走 ``fin_db_async.py``。为了不让"表结构 / 种子数据 /
合规常量"散在两个文件里，统一下沉到本模块：

* ``_ddl()``          —— 建表语句（PG 方言），init 脚本与 async 层共用；
* ``SEED_*``          —— 演示数据，clone 下来直接能跑；
* ``RISK_CEILING`` 等合规常量 —— 规则引擎与 async 数据层共用；
* ``_as_text()``      —— 值转入库文本的小工具。

改表结构只改这里，同步初始化脚本（init_fin_db.py --export-sql）与
async 运行时的自动建表会自动保持一致。
"""
import json

from untils import db_config

# ------------------------------------------------------------------ 风险等级
# 适当性匹配：用户等级 C1~C5 决定他能买到的最高产品风险等级 R1~R5。
# 这里写成一张显式的表而不是一句 if —— 合规规则必须能被单独单测和审计。
RISK_CEILING = {
    "C1": 1,   # 保守型：只能买 R1
    "C2": 1,   # 稳健型：R1
    "C3": 2,   # 平衡型：R2 及以下
    "C4": 3,   # 成长型：R3 及以下
    "C5": 5,   # 激进型：全等级
}

# 单日申购限额（元），按用户风险等级递减
DAILY_LIMIT = {
    "C1": 10_000.0,
    "C2": 50_000.0,
    "C3": 100_000.0,
    "C4": 300_000.0,
    "C5": 1_000_000.0,
}

# 单一产品持仓集中度上限（占账户总资产比例）
CONCENTRATION_LIMIT = 0.4


def _ddl() -> list:
    """生成建表语句（PG 方言）。

    建表脚本与这里同源（``tools/init_fin_db.py --export-sql`` 导出的
    SQL 就是调这个函数拼出来的），改表结构两边自动一致。

    幂等键的 UNIQUE 内联在列上而不是单独建索引，省一条语句也更好读。
    """
    pk = db_config.pk_col()
    s64, s32, s16 = db_config.str_col(64), db_config.str_col(32), db_config.str_col(16)
    txt, num = db_config.text_col(), db_config.num_col()
    return [
        f"""CREATE TABLE IF NOT EXISTS accounts (
            user_id    {s32} PRIMARY KEY,
            name       {s32} NOT NULL,
            risk_level {s16} NOT NULL,
            cash       {num} NOT NULL DEFAULT 0,
            status     {s16} NOT NULL DEFAULT 'active'
        )""",
        f"""CREATE TABLE IF NOT EXISTS products (
            product_code {s32} PRIMARY KEY,
            name         {s64} NOT NULL,
            risk_level   {s16} NOT NULL,
            nav          {num} NOT NULL,
            category     {s32} NOT NULL,
            min_buy      {num} NOT NULL DEFAULT 100,
            status       {s16} NOT NULL DEFAULT 'on_sale'
        )""",
        f"""CREATE TABLE IF NOT EXISTS positions (
            id           {pk},
            user_id      {s32} NOT NULL,
            product_code {s32} NOT NULL,
            shares       {num} NOT NULL DEFAULT 0,
            cost         {num} NOT NULL DEFAULT 0
        )""",
        # client_order_id 的 UNIQUE 是幂等的最后一道防线：
        # 就算应用层判断漏了，数据库也不会让它下第二单
        f"""CREATE TABLE IF NOT EXISTS orders (
            order_id          {pk},
            user_id           {s32} NOT NULL,
            product_code      {s32} NOT NULL,
            action            {s16} NOT NULL,
            amount            {num} NOT NULL,
            status            {s16} NOT NULL,
            client_order_id   {s64} UNIQUE,
            decision_snapshot {txt},
            created_at        {s32} NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS audit_log (
            id       {pk},
            ts       {s32} NOT NULL,
            user_id  {s32},
            action   {s32} NOT NULL,
            payload  {txt},
            result   {s32},
            evidence {txt}
        )""",
        # 合规票据：一次写操作一张票，status 由 issued 单向流转到 consumed / revoked。
        # 状态机写在数据库里而不是内存 dict —— 进程重启票据不该凭空消失，
        # 也不该凭空出现；核销必须是原子的，否则两次下单会用掉同一张票。
        f"""CREATE TABLE IF NOT EXISTS compliance_ticket (
            ticket_id       {s64} PRIMARY KEY,
            thread_id       {s64} NOT NULL,
            user_id         {s32} NOT NULL,
            action          {s32} NOT NULL,
            product_code    {txt},
            amount          {num} NOT NULL DEFAULT 0,
            decision        {s16} NOT NULL DEFAULT 'pass',
            evidence_hash   {s64},
            status          {s16} NOT NULL DEFAULT 'issued',
            issued_at       {s32} NOT NULL,
            expires_at      {s32} NOT NULL,
            consumed_at     {s32},
            tool_call_id    {s64},
            client_order_id {s64}
        )""",
        "CREATE INDEX IF NOT EXISTS idx_ticket_session"
        " ON compliance_ticket(thread_id, status)",
    ]


# 演示数据：让代码 clone 下来就能跑，不需要额外的初始化步骤
SEED_ACCOUNTS = [
    ("u_1001", "张稳健", "C3", 200_000.0),
    ("u_1002", "李成长", "C4", 500_000.0),
    ("u_1003", "王激进", "C5", 1_200_000.0),
    ("u_1004", "赵保守", "C1", 30_000.0),
]
SEED_PRODUCTS = [
    ("000198", "天弘余额宝货币", "R1", 1.0000, "货币型", 1.0),
    ("110020", "易方达沪深300ETF联接", "R3", 1.8420, "指数型", 100.0),
    ("510300", "沪深300ETF", "R3", 3.9210, "股票型", 100.0),
    ("161725", "招商中证白酒指数", "R4", 0.9130, "行业指数", 100.0),
    ("519674", "银河创新成长混合", "R4", 5.2130, "混合型", 100.0),
    ("000001", "华夏成长混合", "R5", 2.1170, "混合型", 100.0),
]
SEED_POSITIONS = [
    ("u_1002", "110020", 10_000.0, 1.7500),
    ("u_1002", "000198", 50_000.0, 1.0000),
    ("u_1003", "510300", 20_000.0, 3.8000),
]


def _as_text(v) -> str:
    """把任意值转成可入库的文本（dict / list 走 JSON）。"""
    if isinstance(v, str):
        return v
    if v is None:
        return ""
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:
        return str(v)
