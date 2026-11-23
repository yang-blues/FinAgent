"""只负责调用模型监控，不负责重试，也不负责业务逻辑
使用钩子函数可以配合Runnable.with_config("callbacks":LLMMonitorCallback)每次程序执行之前执行后自动调用我们的钩子函数做日志输出
"""
import logging
import time
import threading

from uuid import UUID
from langchain_core.callbacks import BaseCallbackHandler


logger = logging.getLogger(__name__)


class LLMMonitorCallback(BaseCallbackHandler):
    """
    统一监控 ChatModel 调用过程。

    记录：
    1. 模型调用耗时
    2. 模型调用成功或失败
    3. 异常类型和异常信息
    """

    def __init__(
        self,
        agent_name: str,
        model_name: str,
    ):
        self.agent_name = agent_name
        self.model_name = model_name

        # 通过 run_id 区分不同模型调用
        self.start_times = {}

        # 保证并发场景下字典读写安全
        self.lock = threading.Lock()

    def on_chat_model_start(
        self,
        serialized: dict,
        messages: list,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        **kwargs,
    ) -> None:
        """模型开始调用时记录开始时间"""

        with self.lock:
            self.start_times[run_id] = time.perf_counter()

        logger.info(
            "LLM_CALL_STARTED | agent=%s | model=%s | run_id=%s",
            self.agent_name,
            self.model_name,
            run_id,
        )

    def on_llm_end(
        self,
        response,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs,
    ) -> None:
        """模型成功返回时记录耗时"""

        with self.lock:
            start_time = self.start_times.pop(run_id, None)

        duration_ms = (
            round((time.perf_counter() - start_time) * 1000, 2)
            if start_time is not None
            else None
        )

        logger.info(
            "LLM_CALL_SUCCESS | agent=%s | model=%s | "
            "duration_ms=%s | run_id=%s",
            self.agent_name,
            self.model_name,
            duration_ms,
            run_id,
        )

        token_usage = self.extract_token_usage(response)
        logger.info("LLM_USAGE_METADATA | data=%s", token_usage)



    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs,
    ) -> None:
        """模型调用失败时记录耗时和异常"""

        with self.lock:
            start_time = self.start_times.pop(run_id, None)

        duration_ms = (
            round((time.perf_counter() - start_time) * 1000, 2)
            if start_time is not None
            else None
        )

        logger.error(
            "LLM_CALL_FAILED | agent=%s | model=%s | "
            "duration_ms=%s | error_type=%s | error=%s | run_id=%s",
            self.agent_name,
            self.model_name,
            duration_ms,
            type(error).__name__,
            str(error)[:500],
            run_id,
        )

    def extract_token_usage(self, response) -> dict:
        """从 LLMResult 中提取 Token 使用情况"""

        default_usage = {
            "usage_available": False,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cache_read": 0,
            "reasoning": 0,
        }

        generations = getattr(response, "generations", None)

        if not generations or not generations[0]:
            return default_usage

        generation = generations[0][0]
        message = getattr(generation, "message", None)

        usage_metadata = getattr(message, "usage_metadata", None)

        if not isinstance(usage_metadata, dict) or not usage_metadata:
            return default_usage

        input_token_details = usage_metadata.get("input_token_details") or {}
        output_token_details = usage_metadata.get("output_token_details") or {}

        return {
            "usage_available": True,
            "input_tokens": usage_metadata.get("input_tokens", 0),
            "output_tokens": usage_metadata.get("output_tokens", 0),
            "total_tokens": usage_metadata.get("total_tokens", 0),
            "cache_read": input_token_details.get("cache_read", 0),
            "reasoning": output_token_details.get("reasoning", 0),
        }
