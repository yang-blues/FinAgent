from langchain_core.documents import Document

from tools.web_search_tool import web_search_tool
from untils.log_utils import log


def web_search(state):
    """
    基于优化后的问题进行网络搜索

    Args:
        state (dict): 当前图状态，包含优化后的问题

    Returns:
        state (dict): 更新后的状态，documents字段替换为网络搜索结果
    """
    log.info("---WEB SEARCH---")  # 阶段标识
    question = state["question"]  # 获取优化后的问题

    # 执行网络搜索
    resp = web_search_tool.invoke({"query": question})
    results = resp.get("results", [])
    web_results = "\n".join([r["content"] for r in results])
    web_results = Document(page_content=web_results)  # 转换为文档格式

    return {"documents": web_results, "question": question}  # 返回更新状态