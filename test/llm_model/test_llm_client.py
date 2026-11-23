
import unittest

from langchain_core.runnables import RunnableLambda

from llm_model.llm_client import build_reliable_runnable
from openai import AuthenticationError, InternalServerError
from httpx import Request, Response

class TestLLMClient(unittest.TestCase):

    # def test_normal_call(self):
    #     """正常调用：第一次成功，不应该重试"""
    #     call_count = 0
    #
    #     def fake_llm(state):
    #         nonlocal call_count
    #         call_count += 1
    #         return "success"
    #
    #     runnable = RunnableLambda(fake_llm)
    #
    #     result = runnable.invoke({"messages": []})
    #
    #     self.assertEqual(result, "success")
    #     self.assertEqual(call_count, 1)
    #
    # def test_retry_success(self):
    #     """第一次超时，第二次成功"""
    #     call_count = 0
    #
    #     def fake_llm(state):
    #         nonlocal call_count
    #         call_count += 1
    #
    #         if call_count == 1:
    #             raise TimeoutError("模拟模型请求超时")
    #
    #         return "success"
    #
    #     runnable = build_reliable_runnable(RunnableLambda(fake_llm),wait_exponential_jitter=False)
    #
    #
    #     result = runnable.invoke({"messages": []})
    #
    #     self.assertEqual(result, "success")
    #     self.assertEqual(call_count, 2)
    #
    # def test_retry_exhausted(self):
    #     """连续超时：达到最大尝试次数后抛出异常"""
    #     call_count = 0
    #
    #     def fake_llm(state):
    #         nonlocal call_count
    #         call_count += 1
    #         raise TimeoutError("模拟模型请求超时")
    #
    #     runnable = build_reliable_runnable(RunnableLambda(fake_llm))
    #
    #     with self.assertRaises(TimeoutError):
    #         runnable.invoke({"messages": []})
    #
    #     self.assertEqual(call_count, 3)
    #
    # def test_no_retry_for_other_exception(self):
    #     """非指定异常：不应该触发重试"""
    #     call_count = 0
    #
    #     def fake_llm(state):
    #         nonlocal call_count
    #         call_count += 1
    #         raise ValueError("模拟参数错误")
    #
    #     runnable = build_reliable_runnable(RunnableLambda(fake_llm))
    #
    #     with self.assertRaises(ValueError):
    #         runnable.invoke({"messages": []})
    #
    #     self.assertEqual(call_count, 1)

    def test_no_retry_for_authentication_error(self):
        """认证失败：不应该触发重试"""
        call_count = 0

        request = Request("POST", "https://api.example.com/v1/chat/completions")
        response = Response(
            status_code=401,
            request=request
        )
        error = AuthenticationError(
            "API Key 无效",
            response=response,
            body=None
        )

        def fake_llm(state):
            nonlocal call_count
            call_count += 1
            raise error

        runnable = build_reliable_runnable(
            RunnableLambda(fake_llm)
        )

        with self.assertRaises(AuthenticationError):
            runnable.invoke({"messages": []})

        self.assertEqual(call_count, 1)

    def test_retry_for_internal_server_error(self):
        """服务端错误：应该触发重试"""
        call_count = 0

        request = Request("POST", "https://api.example.com/v1/chat/completions")
        response = Response(
            status_code=500,
            request=request
        )
        error = InternalServerError(
            "模拟服务器内部错误",
            response=response,
            body=None
        )

        def fake_llm(state):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                raise error

            return "success"

        runnable = build_reliable_runnable(
            RunnableLambda(fake_llm),
            max_attempts=3
        )

        result = runnable.invoke({"messages": []})

        self.assertEqual(result, "success")
        self.assertEqual(call_count, 2)

    def test_prompt_with_reliable_llm(self):
        """Prompt 与 Reliable LLM 组合后能够正常执行"""
        call_count = 0

        def fake_llm(state):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                raise TimeoutError("模拟超时")

            return "success"

        prompt = RunnableLambda(lambda state: state)

        reliable_llm = build_reliable_runnable(
            RunnableLambda(fake_llm),
            max_attempts=3,
            retry_exceptions=(TimeoutError,),
            wait_exponential_jitter=False,
        )

        chain = prompt | reliable_llm

        result = chain.invoke({"messages": []})

        self.assertEqual(result, "success")
        self.assertEqual(call_count, 2)


if __name__ == "__main__":
    unittest.main()
