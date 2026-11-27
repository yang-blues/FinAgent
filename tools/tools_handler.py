from langchain_core.runnables import RunnableLambda
from langgraph.prebuilt import ToolNode
from tools.runtime.interceptor import ToolInterceptor
from tools.runtime.registry import ToolPolicyRegistry
from untils.log_utils import log


def create_tool_node_with_fallback(
    tools: list,
    tool_policy_registry: ToolPolicyRegistry,
):
    """
    创建带执行策略拦截和兜底机制的工具节点。

    Args:
        tools: 当前 Agent 可使用的工具列表。
        tool_policy_registry: 全局工具策略注册表。

    Returns:
        配置了执行策略的 ToolNode。
    """
    interceptor = ToolInterceptor(tool_policy_registry)

    return ToolNode(
        tools,
        handle_tool_errors=False,
        wrap_tool_call=interceptor.tool_call_interceptor,
        awrap_tool_call=interceptor.async_tool_call_interceptor,
    )






