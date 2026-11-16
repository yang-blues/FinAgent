from langgraph.prebuilt import tools_condition
from langgraph.constants import END

from graph_fin.base_data_model import ToResearchAssistant, ToMarketAssistant, ToTradeAssistant, CompleteOrEscalate
from graph_fin.compliance import extract_write_intent
from graph_fin.state import State
from untils.log_utils import log


#主agent路由
def route_primary_assistant(state:State):
    """主助理的条件边：按结构化委派模型跳转，是**确定性路由**。
    """
    route = tools_condition(state)#如果有工具调用返回返回tools否则返回END
    if route == END:
        return END
    tool_calls = state["messages"][-1].tool_calls
    if not tool_calls:
        return END
    name = tool_calls[0]["name"]
    mapping = {
        ToResearchAssistant.__name__: "research",
        ToMarketAssistant.__name__: "market",
        ToTradeAssistant.__name__: "trade",
    }
    if name in mapping:
        return mapping[name]
    return "primary_assistant_tools"

def route_after_child(state: State):
    """wrapper之后，子助理是否主动交还控制权
    子图结束时把 escalate 的 ToolMessage 留在总线上，这里向后找最近的
    一条 AIMessage 判断它是不是 CompleteOrEscalate：
        - 是 → 回主助理（可能需要重新委派或改方案）
        - 不是 → 子助理已给出最终回答，本轮 END
    """
    for msg in reversed(state.get("messages", [])):
        if getattr(msg,"type","") == "ai":
            calls = msg.tool_calls or []
            if any(tc["name"] == CompleteOrEscalate.__name__ for tc in calls):
                return "primary_assistant"
            return END
    return END
#子助理路由
def _has_escalate(state:dict) -> bool:
    """子助理是否请求交还控制权"""
    tool_calls = state["messages"][-1].tool_calls or []
    #如果有一条工具是要求返回主节点就返回
    return any(tc["name"] == CompleteOrEscalate.__name__ for tc in tool_calls)
#投研助理的路由
def route_research(state: dict):
    """
    路由投研助理的输出。

    :param state: 当前状态
    :return: 下一个节点名
    """
    route = tools_condition(state)
    if route == END:
        return END
    if _has_escalate(state):
        return "exit"
    return "research_tools"
#行情助理的路由
def route_market(state: dict):
    """
    路由行情助理的输出。

    :param state: 当前状态
    :return: 下一个节点名
    """
    route = tools_condition(state)
    if route == END:
        return END
    if _has_escalate(state):
        return "exit"
    return "market_tools"
#交易助手的路由
def route_after_trade_assistant(state: dict):
    """
    路由交易助理的输出，这是全项目最关键的一条条件边。

    逻辑：
        - 没有 tool_calls → END
        - escalation → leave_skill
        - 命中 sensitive → compliance_check（**无条件**强制闸门）
        - 其余 → trade_safe_tools（不打断）

    为什么这里不做票据校验：条件边只能读 State 快照，而票据被核销后
    快照里的字段仍然残留，拿它判断"要不要合规"必然出错（上一版就是这么
    漏掉重复交易的）。现在票据只在一个地方校验——写工具第一行的原子核销
    （``UPDATE ... RETURNING``，用过即废、过期即废），校验与作废同一条 SQL。

    :param state: 当前状态
    :return: 下一个节点名
    """
    route = tools_condition(state)
    if route == END:
        return END
    if _has_escalate(state):
        return "exit"
    if extract_write_intent(state["messages"]):
        log.info("检测到写操作，强制进入合规核查")
        return "compliance_check"
    return "trade_safe_tools"

