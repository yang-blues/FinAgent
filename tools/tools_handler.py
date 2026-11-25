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

    tool_node = ToolNode(
        tools,
        wrap_tool_call=interceptor.tool_call_interceptor,
        awrap_tool_call=interceptor.async_tool_call_interceptor,
    )
    #toolnode节点会自己捕获异常，有可能我们外部的就没用了
    return tool_node.with_fallbacks(
        [RunnableLambda(handle_tool_error)], exception_key="error"
    )

def handle_tool_error(state) -> dict:
    """
    处理工具调用时发生错误，根据tool_call_id手动封装一条toolMessage
    参数:
        state (dict): 当前状态，含 error 与 messages。
    返回:
        dict: 新的消息列表。
    """
    error = state.get("error")
    tool_calls = state['messages'][-1].tool_calls
    log.warning(f"工具调用失败，回灌模型自愈：{repr(error)[:200]}")
    from langchain_core.messages import ToolMessage
    return {
        "messages":[
            ToolMessage(
                content=f"错误：{repr(error)}\n请修正您的错误",
                tool_call_id=tc["id"],
            )
            for tc in tool_calls
        ]
    }





