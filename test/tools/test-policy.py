import unittest

from tools.runtime.policy import ToolPolicy, ToolType


class TestToolPolicy(unittest.TestCase):
    def test_safe_retry_3_times_ok(self):
        # SAFE，允许重试，3 次
        policy = ToolPolicy(ToolType.SAFE, timeout=5.0, max_attempts=3, retryable=True)
        self.assertEqual(policy.tool_type, ToolType.SAFE)
        self.assertEqual(policy.max_attempts, 3)
        self.assertTrue(policy.retryable)

    def test_safe_no_retry_1_ok(self):
        # SAFE，禁止重试，1 次
        policy = ToolPolicy(ToolType.SAFE, timeout=5.0, max_attempts=1, retryable=False)
        self.assertEqual(policy.max_attempts, 1)
        self.assertFalse(policy.retryable)

    def test_sensitive_no_retry_1_ok(self):
        # SENSITIVE，禁止重试，1 次
        policy = ToolPolicy(ToolType.SENSITIVE, timeout=5.0, max_attempts=1, retryable=False)
        self.assertEqual(policy.tool_type, ToolType.SENSITIVE)

    def test_sensitive_retry_raise_value_error(self):
        # SENSITIVE，允许重试 → ValueError
        with self.assertRaises(ValueError) as cm:
            ToolPolicy(ToolType.SENSITIVE, timeout=5.0, max_attempts=2, retryable=True)
        self.assertEqual(str(cm.exception), "敏感工具不允许自动重试")

    def test_timeout_le_zero_raise_value_error(self):
        # timeout <= 0
        with self.assertRaises(ValueError) as cm:
            ToolPolicy(ToolType.SAFE, timeout=0, max_attempts=1, retryable=False)
        self.assertEqual(str(cm.exception), "timeout 必须大于 0")

        with self.assertRaises(ValueError):
            ToolPolicy(ToolType.SAFE, timeout=-2, max_attempts=1, retryable=False)

    def test_max_attempts_lt_1_raise_value_error(self):
        # max_attempts < 1
        with self.assertRaises(ValueError) as cm:
            ToolPolicy(ToolType.SAFE, timeout=5, max_attempts=0, retryable=False)
        self.assertEqual(str(cm.exception), "max_attempts 必须大于等于 1")

    def test_not_retryable_but_max_attempts_not_1(self):
        # 禁止重试但 max_attempts 为 3
        with self.assertRaises(ValueError) as cm:
            ToolPolicy(ToolType.SAFE, timeout=5, max_attempts=3, retryable=False)
        self.assertEqual(str(cm.exception), "禁止重试的工具 max_attempts 必须为 1")

    def test_tool_type_str_raise_type_error(self):
        # tool_type 传入字符串
        with self.assertRaises(TypeError) as cm:
            ToolPolicy("safe", timeout=5, max_attempts=1, retryable=False)
        self.assertEqual(str(cm.exception), "tool_type 必须是 ToolType 类型")

if __name__ == "__main__":
    unittest.main()