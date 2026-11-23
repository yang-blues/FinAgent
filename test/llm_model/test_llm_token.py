
import unittest
from unittest.mock import Mock

from llm_model.callbacks import LLMMonitorCallback


class TestExtractTokenUsage(unittest.TestCase):

    def setUp(self):
        self.callback = LLMMonitorCallback(
            agent_name="primary",
            model_name="qwen3.8-max-0902",
        )

    def create_response(self, usage_metadata):
        """构造模拟的 LLMResult 返回对象"""
        message = Mock()
        message.usage_metadata = usage_metadata

        generation = Mock()
        generation.message = message

        response = Mock()
        response.generations = [[generation]]

        return response

    def test_normal_usage(self):
        """正常提取 Token 使用情况"""
        usage_metadata = {
            "input_tokens": 2924,
            "output_tokens": 299,
            "total_tokens": 3223,
            "input_token_details": {"cache_read": 1024},
            "output_token_details": {"reasoning": 82},
        }

        response = self.create_response(usage_metadata)

        result = self.callback.extract_token_usage(response)

        self.assertEqual(result["usage_available"], True)
        self.assertEqual(result["input_tokens"], 2924)
        self.assertEqual(result["output_tokens"], 299)
        self.assertEqual(result["total_tokens"], 3223)
        self.assertEqual(result["cache_read"], 1024)
        self.assertEqual(result["reasoning"], 82)

    def test_response_is_none(self):
        """response 为 None"""
        result = self.callback.extract_token_usage(None)

        self.assertFalse(result["usage_available"])
        self.assertEqual(result["total_tokens"], 0)

    def test_generations_is_empty(self):
        """generations 为空"""
        response = Mock()
        response.generations = []

        result = self.callback.extract_token_usage(response)

        self.assertFalse(result["usage_available"])

    def test_first_generation_is_empty(self):
        """第一组 generation 为空"""
        response = Mock()
        response.generations = [[]]

        result = self.callback.extract_token_usage(response)

        self.assertFalse(result["usage_available"])

    def test_usage_metadata_is_none(self):
        """usage_metadata 为 None"""
        response = self.create_response(None)

        result = self.callback.extract_token_usage(response)

        self.assertFalse(result["usage_available"])

    def test_missing_token_fields(self):
        """缺少部分 Token 字段"""
        response = self.create_response({
            "input_tokens": 100,
            "input_token_details": {},
            "output_token_details": {},
        })

        result = self.callback.extract_token_usage(response)

        self.assertTrue(result["usage_available"])
        self.assertEqual(result["input_tokens"], 100)
        self.assertEqual(result["output_tokens"], 0)
        self.assertEqual(result["total_tokens"], 0)
        self.assertEqual(result["cache_read"], 0)
        self.assertEqual(result["reasoning"], 0)

    def test_token_details_are_none(self):
        """Token 细分信息为 None"""
        response = self.create_response({
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "input_token_details": None,
            "output_token_details": None,
        })

        result = self.callback.extract_token_usage(response)

        self.assertTrue(result["usage_available"])
        self.assertEqual(result["cache_read"], 0)
        self.assertEqual(result["reasoning"], 0)


if __name__ == "__main__":
    unittest.main()
