
from tools.runtime.policy import ToolPolicy, ToolType


class ToolPolicyRegistry:
    """
    Tool策略注册表

    负责管理模型中的可执行工具及其对应的策略
    """

    def __init__(self):
        self._tools_policy:dict[str, ToolPolicy] = {}

    def register(self,tool_name:str, tool_policy:ToolPolicy):
        if not tool_name or not isinstance(tool_name, str):
            raise ValueError("tool_name 必须是非空字符串")

        if not isinstance(tool_policy, ToolPolicy):
            raise TypeError("tool_policy 必须是 ToolPolicy 类型")

        if tool_name in self._tools_policy:
            raise KeyError(f"Tool {tool_name} 不允许重复注册")

        self._tools_policy[tool_name] = tool_policy

    def get_policy(self,tool_name:str) -> ToolPolicy:
        if tool_name not in self._tools_policy:
            raise KeyError(f"Tool {tool_name} 没有注册")
        return self._tools_policy[tool_name]
    def has_policy(self,tool_name:str) -> bool:
        return tool_name in self._tools_policy

    def register_tool_policy(self,
                             safe_tools:list,
                             sensitive_tools:list):
        """统一注册工具执行策略"""
        safe_policy = ToolPolicy(
            tool_type=ToolType.SAFE,
            timeout=30,
            max_attempts=3,
            retryable=True,

        )
        sensitive_tool_policy = ToolPolicy(
            tool_type=ToolType.SENSITIVE,
            timeout=30,
            max_attempts=1,
            retryable=False,
        )

        #按照工具名称去重，同时保留原始顺序
        safe_tool_names = dict.fromkeys(
            tool.name for tool in safe_tools
        )
        sensitive_tool_names = dict.fromkeys(
            tool.name for tool in sensitive_tools
        )

        #检查是否存在策略冲突
        conflicts = safe_tool_names.keys() & sensitive_tool_names.keys()

        if conflicts:
            raise ValueError(
                f"工具不能同时属于SAFE和SENSITIVE：{list(conflicts)}"
            )
        #注册SAFE工具
        for tool_name in safe_tool_names:
            self.register(tool_name, safe_policy)
        #注册SENSITIVE工具
        for tool_name in sensitive_tool_names:
            self.register(tool_name, sensitive_tool_policy)