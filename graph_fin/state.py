"""图的状态定义：父图最小总线 + 三个子图私有 schema。
架构（私有 schema + wrapper）
"""
from typing import  TypedDict, Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages

class State(TypedDict):
    """父图状态 = 最小共享总线。

    字段:
        messages: 对话消息总线。子图的中间消息（tool_call / tool_result）
                  会经由 wrapper 回传合并到这里。
        user_profile: 用户画像（风险等级、账户、适当性）。每轮进图时重新
                      查库写入，不让模型从对话历史里"回忆"——回忆错了
                      就是适当性事故。
        summary: 被压缩掉的历史对话摘要（见 graph_fin/memory.py）。
                 超过阈值时老消息从 messages 中移除，浓缩成这一段文本，
                 只注入主助理 prompt，不进子图 schema。
    """
    messages: Annotated[list[AnyMessage], add_messages]
    user_profile: str
    summary: str
class ChildState(TypedDict):
    """投研 / 行情子图的私有状态：只有消息史，没有别的。"""

    messages: Annotated[list[AnyMessage], add_messages]
class TradeState(TypedDict):
    """交易子图的私有状态：合规中间态全部封在这里。

    字段:
        messages: 消息史（进子图时从父总线拷贝，出去时只回传最终结果）。
        compliance_decision: 合规三态 pass / block / insufficient_evidence。
        compliance_evidence: 合规证据文本（进审批卡片给人核对）。
        compliance_warnings: 集中度提示这类"不拦截但要说"的告警。
        approval_decision: 人工审批结论 approved / rejected，
                           由 approval_node 写入，供其后条件边路由。
    """

    messages: Annotated[list[AnyMessage], add_messages]
    compliance_decision: str
    compliance_evidence: str
    compliance_warnings: list
    approval_decision: str


