"""工具增强"""
import logging
import time

from tools.runtime.registry import ToolPolicyRegistry

logger = logging.getLogger(__name__)

# 允许自动重试的异常白名单
RETRYABLE_TOOL_EXCEPTIONS = (
    TimeoutError,
    ConnectionError,
)

class ToolInterceptor:
    """工具执行拦截器"""
    def __init__(self,tool_policy_registry: ToolPolicyRegistry):
        self.tool_policy_registry = tool_policy_registry

    def tool_call_interceptor(self,request,execute):
        """
        同步工具调用拦截器
        Args:
            request:工具的执行请求
            execute:工具的执行器
        Returns:
            工具的执行结果
        """
        tool_name = request.tool_call["name"]
        # 1.获取当前工具对应的执行策略
        tool_policy = self.tool_policy_registry.get_policy(tool_name)
        start_time = time.perf_counter()
        #retryable=False时，策略模型保证max_attempts = 1
        max_attempts = (
            tool_policy.max_attempts
            if tool_policy.retryable
            else 1
        )
        try:
            for attempt in range(1,max_attempts+1):
                try:
                    logger.info(
                        "工具开始 | 工具名称=%s | 执行次数=%s",
                        tool_name,
                        attempt,
                    )
                    # 2.执行原始工具
                    result = execute(request)
                    logger.info(
                    "工具执行成功 | 工具名称=%s | 执行次数=%s",
                    tool_name,
                        attempt,
                    )

                    return result
                except RETRYABLE_TOOL_EXCEPTIONS as e:
                    # 满足重试条件时继续循环
                    if attempt >= max_attempts:
                        logger.exception(
                            "工具重试次数用尽 | 工具名称=%s | 尝试次数=%s |异常类型=%s",
                            tool_name,
                            attempt,
                            type(e).__name__,
                        )
                        #重试次数耗尽跳出循环抛出异常
                        raise
                    logger.warning(
                        "工具尝试重试 | 工具名称=%s | 尝试次数=%s | 异常类型=%s",
                        tool_name,
                        attempt,
                        type(e).__name__,
                    )
                except Exception as e:
                    # 其他异常直接抛出，不再重试
                    logger.exception(
                        "工具执行失败 | 工具名称=%s | 尝试次数=%s | 异常类型=%s",
                        tool_name,
                        attempt,
                        type(e).__name__,
                    )
                    raise
        finally:
                duration_ms = (
                    time.perf_counter() - start_time
                ) * 1000

                logger.info(
                    "工具调用结束 | 工具名称=%s | duration_ms=%.2f",
                    tool_name,
                    duration_ms,
                )


    async def async_tool_call_interceptor(self,request,execute):
        """
        异步工具调用拦截器
        """
        tool_name = request.tool_call["name"]
        # 1.获取当前工具对应的执行策略
        tool_policy = self.tool_policy_registry.get_policy(tool_name)
        start_time = time.perf_counter()
        # retryable=False时，策略模型保证max_attempts = 1
        max_attempts = (
            tool_policy.max_attempts
            if tool_policy.retryable
            else 1
        )
        try:
            for attempt in range(1, max_attempts + 1):
                try:
                    logger.info(
                        "工具开始 | 工具名称=%s | 执行次数=%s",
                        tool_name,
                        attempt,
                    )
                    # 2.执行原始工具
                    result =await execute(request)
                    logger.info(
                        "工具执行成功 | 工具名称=%s | 执行次数=%s",
                        tool_name,
                        attempt,
                    )

                    return result
                except RETRYABLE_TOOL_EXCEPTIONS as e:
                    # 满足重试条件时继续循环
                    if attempt >= max_attempts:
                        logger.exception(
                            "工具重试次数用尽 | 工具名称=%s | 尝试次数=%s |异常类型=%s",
                            tool_name,
                            attempt,
                            type(e).__name__,
                        )
                        # 重试次数耗尽跳出循环抛出异常
                        raise
                    logger.warning(
                        "工具尝试重试 | 工具名称=%s | 尝试次数=%s | 异常类型=%s",
                        tool_name,
                        attempt,
                        type(e).__name__,
                    )
                except Exception as e:
                    # 其他异常直接抛出，不再重试
                    logger.exception(
                        "工具执行失败 | 工具名称=%s | 尝试次数=%s | 异常类型=%s",
                        tool_name,
                        attempt,
                        type(e).__name__,
                    )
                    raise
        finally:
            duration_ms = (
                time.perf_counter() - start_time
            ) * 1000

            logger.info(
                "工具调用结束 | 工具名称=%s | duration_ms=%.2f",
                tool_name,
                duration_ms,
            )