"""统一构建带有可靠性机制的 Runnable
LLMClient 不应该知道FinAgent有哪些Agent,也不知道某个Prompt是做什么的。
只负责让模型调用更可靠"""
from langchain_core.runnables import Runnable
from openai import (
    APITimeoutError,
    APIConnectionError,
    RateLimitError,
    InternalServerError,
)

RETRY_EXCEPTIONS = (
    APITimeoutError,      #请求超时
    APIConnectionError,   #网络连接异常
    RateLimitError,       #请求频率或配额限制(429)
    InternalServerError,  #服务端内部错误(通常是5xx)
)
DEFAULT_RETRY_PARAMS = {
    "initial": 1, #初始等待1秒
    "max": 8,     # 最大等待不超过8秒
    "exp_base": 2,# 每次等待时间按2的指数增加
    "jitter": 1,  #增加0~1秒的随机等待
}


def build_reliable_runnable(
        runnable:Runnable,
        max_attempts:int = 3,
        retry_exceptions:tuple = RETRY_EXCEPTIONS,
        wait_exponential_jitter: bool = True,
        exponential_jitter_params: dict | None = None,
) -> Runnable:
    """
    为Runnable增加有限重试能力

    Args:
        runnable:原始模型调用Runnable
        max_attempts:最大尝试次数，包含第一次模型调用
        retry_exceptions:允许触发重试的异常类型
        wait_exponential_jitter:开启指数退避+随机抖动等待策略
        exponential_jitter_params:重试策略的参数配置
    Returns:
        增强后的Runnable
    """
    if max_attempts < 1:
        raise ValueError("max_attempts 必须要 >= 1")

    if exponential_jitter_params is None:
        exponential_jitter_params = DEFAULT_RETRY_PARAMS.copy()

    return runnable.with_retry(
        retry_if_exception_type=retry_exceptions,
        stop_after_attempt=max_attempts,
        wait_exponential_jitter=wait_exponential_jitter,
        exponential_jitter_params=exponential_jitter_params,
    )