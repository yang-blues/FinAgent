"""主图组装：把三个子助理挂到主助理上，编译出可服务的图"""
from langgraph.graph import StateGraph,START,END

from graph_fin.agent_assistant import primary_runnable, primary_tools
from graph_fin.assistant import FinAssistant
from graph_fin.build_child_graph import build_research_graph, build_market_graph, build_trade_graph
from graph_fin.get_user_profile_node import get_user_profile
from graph_fin.memory import memory_compression_node
from graph_fin.route_fin import route_primary_assistant, route_after_child
from graph_fin.state import State
from graph_fin.wrapper_nodes import create_wrapper
from tools.tools_handler import create_tool_node_with_fallback



def build_graph(**kwargs) -> StateGraph:
    """组装主图（未编译）。

    返回:
        StateGraph: 组装好的图对象。
    """
    #行情搜索的mcp工具
    stock_tools = kwargs.get("stock_tools", [])
    checkpointer = kwargs.get("checkpointer", None)


    builder = StateGraph(State)
    builder.add_node("fetch_user_profile",get_user_profile)
    builder.add_node("compress_memory",memory_compression_node)

    builder.add_edge(START,"fetch_user_profile")
    builder.add_edge("fetch_user_profile","compress_memory")
    # 三个子图：独立编译 + wrapper 挂载（私有 schema ↔ 总线的翻译层）
    builder.add_node("research",create_wrapper(
        build_research_graph(checkpointer), "research"
    ))
    builder.add_node("market", create_wrapper(
        build_market_graph(stock_tools,checkpointer), "market"
    ))
    builder.add_node("trade", create_wrapper(
        build_trade_graph(checkpointer), "trade"
    ))
    for child in ("research","market","trade"):
        builder.add_conditional_edges(
            child,route_after_child,
        ["primary_assistant",END])
    builder.add_node("primary_assistant", FinAssistant(primary_runnable))
    builder.add_edge("compress_memory", "primary_assistant")
    builder.add_node("primary_assistant_tools",
                     create_tool_node_with_fallback(primary_tools))

    builder.add_conditional_edges(
        "primary_assistant", route_primary_assistant,
        ["research", "market", "trade",
         "primary_assistant_tools", END])
    builder.add_edge("primary_assistant_tools", "primary_assistant")


    return builder

