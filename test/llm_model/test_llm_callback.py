import unittest
from uuid import uuid4

from llm_model.callbacks import LLMMonitorCallback


class TestLLMMonitorCallback(unittest.TestCase):

    def setUp(self):
        self.callback = LLMMonitorCallback(
            agent_name="test_agent",
            model_name="test_model",
        )

    def test_call_success(self):
        """模型成功返回后，清理调用开始时间"""

        run_id = uuid4()

        self.callback.on_chat_model_start(
            serialized={},
            messages=[],
            run_id=run_id,
        )
        #当开始的时候run_id在start_times里面
        self.assertIn(run_id, self.callback.start_times)

        self.callback.on_llm_end(
            response=None,
            run_id=run_id,
        )
        # 当结束的时候run_id没在start_times里面，被清除出去了
        self.assertNotIn(run_id, self.callback.start_times)

    def test_call_error(self):
        """模型调用失败后，清理调用开始时间"""

        run_id = uuid4()

        self.callback.on_chat_model_start(
            serialized={},
            messages=[],
            run_id=run_id,
        )

        self.callback.on_llm_error(
            error=TimeoutError("模拟请求超时"),
            run_id=run_id,
        )

        self.assertNotIn(run_id, self.callback.start_times)


if __name__ == "__main__":
    unittest.main()