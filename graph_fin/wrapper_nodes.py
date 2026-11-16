"""wrapper 节点：父图与子图之间的显式翻译层。
由于我们不同Agent之间做了状态的隔离所以我们想要不同Agent之间能做信息传递那么就必须编写映射函数
"""
from typing import Callable

from langchain_core.runnables import RunnableConfig
from untils.log_utils import log


def create_wrapper(child_graph,name:str) -> Callable:
    """工厂：为一个已编译的子图生成挂进父图的wrapper节点

    :param child_graph: 编译时已挂 checkpointer 的子图。
    :param name: 节点名（用于日志与子图检查点的 ns 前缀）。
    :return: 异步节点函数 (state, config) -> 状态增量。
    """

    async def wrapper(state:dict,config:RunnableConfig) -> dict:
        log.info(f"[{name}] 进入子图（消息 {len(state.get('messages', []))} 条）")
        #取出主agent和子agent之间共享的上下文
        child_input = {"messages":state.get('messages', [])}
        result = await child_graph.ainvoke(child_input,config)
        #取出子图增加的上下文，写到我们的共享state中
        messages = result.get('messages', []) if result else []
        return {"messages":messages}
    #根据不同的子agent将这个映射函数改成不同的名字
    wrapper.__name__ = name
    return wrapper