# -*- coding: utf-8 -*-
"""异步数据库引擎配置：SQLAlchemy 2.0 AsyncSession + asyncpg。

与 ``untils/db_config.py``（同步 psycopg2）并存的原因
----------------------------------------------------
第二步改造完成后，**业务运行时全部走本模块**：async 工具（fin_tools）、
图节点（compliance / ticket / get_user_profile）、审批路由（routes）
统一经 ``tools/fin_db_async.py`` 访问数据库。
同步层只剩初始化脚本（``tools/init_fin_db.py``）在用，与运行时互不影响。

连接串与同步层共用 ``FINAGENT_DB_URL``，只是 driver 换成 asyncpg：
    postgresql+asyncpg://postgres:***@127.0.0.1:5432/finagent

注意事项
--------
* asyncpg **不支持** psycopg2 的 ``%s`` 参数风格，SQLAlchemy 的 ``text()``
  统一用 ``:name`` 命名参数——业务 SQL 翻译时占位符要跟着改。
* ``pool_pre_ping=True`` 接管了同步层手写的探活 + INERROR rollback 逻辑。
* engine 模块级创建、惰性连接；应用退出时调 ``close_async_engine()``。
"""
import os
import re

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv(override=False)

# 与同步层同一环境变量，driver 强制 asyncpg
_ASYNC_DB_URL = (os.getenv("FINAGENT_DB_URL",
                           "postgresql+psycopg2://postgres:yang1258@127.0.0.1:5432/finagent")
                 ).strip().replace("+psycopg2", "+asyncpg")

# 编译期校验：只放行 postgres + asyncpg
_u = make_url(_ASYNC_DB_URL)
if not (_u.drivername or "").lower().startswith("postgresql+asyncpg"):
    raise ValueError(
        f"异步层只支持 postgresql+asyncpg，当前 drivername={_u.drivername!r}")

# 唯一约束冲突等完整性异常——幂等逻辑 catch 它（asyncpg 的 UniqueViolation
# 会被 SQLAlchemy 包装成 IntegrityError，上层不需要感知方言差异）
from sqlalchemy.exc import IntegrityError  # noqa: E402
INTEGRITY_ERRORS = (IntegrityError,)

engine = create_async_engine(
    _ASYNC_DB_URL,
    pool_pre_ping=True,     # 每次取连接前探活，断线自动重建（替代手写 _is_alive）
    pool_size=5,            # Agent 工具并发不高，默认池够用
    max_overflow=10,
    pool_recycle=1800,      # 防止 PG 侧空闲连接被掐
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False,
)


def safe_dsn_async() -> str:
    """脱敏连接串（/health 与日志用）。"""
    return re.sub(r"//([^:/@]+):[^@]*@", r"//\1:***@", _ASYNC_DB_URL)


async def close_async_engine():
    """应用退出时释放连接池（main.py lifespan 收尾时调用）。"""
    await engine.dispose()


# ------------------------------------------------------------------ 执行助手
def _named(sql: str, params) -> tuple:
    """把 psycopg2 风格 %s 占位符的 SQL 翻译成 text() + 命名参数。

    本模块内所有 SQL 直接写 :name 风格，这个助手只用于测试对照，
    业务代码请直接写命名参数，不要依赖自动翻译。
    """
    return sql, dict(params) if isinstance(params, dict) else params


async def fetch_all(session: AsyncSession, sql: str, params=None) -> list[dict]:
    """执行查询返回 dict 列表（等价同步层的 RealDictCursor.fetchall）。"""
    rows = await session.execute(text(sql), params or {})
    return [dict(r) for r in rows.mappings().all()]


async def fetch_one(session: AsyncSession, sql: str, params=None) -> dict | None:
    """执行查询返回单个 dict 或 None（等价 fetchone）。"""
    rows = await session.execute(text(sql), params or {})
    row = rows.mappings().first()
    return dict(row) if row else None


def dsn_debug() -> str:
    return safe_dsn_async()


if __name__ == "__main__":
    import asyncio

    async def _smoke():
        async with AsyncSessionLocal() as s:
            v = (await s.execute(text("SELECT 1 AS one"))).scalar()
            print("连接可用:", v == 1, "|", safe_dsn_async())

    asyncio.run(_smoke())
