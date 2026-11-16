"""
记忆管理模块
"""
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    ToolMessage,
    RemoveMessage,
)
from langchain_core.prompts import ChatPromptTemplate

from llm_model.all_llm import llm

"""记忆压缩"""



def select_messages_to_compress(messages):
    """
    选择需要压缩的历史消息：
    1. 保留最新的 HumanMessage 及其之后的消息。
    2. 检查 AIMessage.tool_calls 和 ToolMessage 是否完整配对。
    3. 不压缩不完整的工具调用。
    """

    if not messages:
        return []

    # 找到最新一条 HumanMessage
    latest_human_index = None

    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            latest_human_index = index
            break

    if latest_human_index is None:
        return []

    # 当前用户问题之前的消息才有资格被压缩
    candidates = messages[:latest_human_index]

    # 从末尾向前收缩，保证工具调用配对完整
    while candidates:
        tool_call_ids = set()
        tool_message_ids = set()

        for msg in candidates:
            if isinstance(msg, AIMessage):
                for tool_call in msg.tool_calls:
                    if tool_call.get("id"):
                        tool_call_ids.add(tool_call["id"])

            elif isinstance(msg, ToolMessage):
                if msg.tool_call_id:
                    tool_message_ids.add(msg.tool_call_id)

        # 每一个 Tool Call 都必须有对应的 ToolMessage
        calls_complete = tool_call_ids.issubset(tool_message_ids)

        # 每一个 ToolMessage 也必须能找到对应的 Tool Call
        results_complete = tool_message_ids.issubset(tool_call_ids)

        if calls_complete and results_complete:
            break

        # 不完整时，保留最后一条消息，不参与压缩
        candidates = candidates[:-1]

    return candidates

def messages_to_text(messages):
    """
    将 LangChain 消息转换为适合 LLM 阅读的文本。
    保留角色、工具调用参数和工具执行结果。
    """

    transcript = []

    for msg in messages:

        if isinstance(msg, HumanMessage):
            role = "用户"

        elif isinstance(msg, AIMessage):
            role = "AI"

        elif isinstance(msg, ToolMessage):
            role = f"工具({msg.name or 'unknown'})"

        else:
            role = "其他"

        content = str(msg.content)

        # 保留 AI 的工具调用信息
        if isinstance(msg, AIMessage) and msg.tool_calls:
            tool_calls = []

            for call in msg.tool_calls:
                tool_calls.append(
                    f"工具名称：{call.get('name')}\n"
                    f"调用参数：{call.get('args')}\n"
                    f"调用ID：{call.get('id')}"
                )

            content += "\n工具调用：\n" + "\n".join(tool_calls)

        # 保留工具调用对应的 ID
        if isinstance(msg, ToolMessage):
            content += f"\n对应调用ID：{msg.tool_call_id}"

        transcript.append(
            f"【{role}】\n{content}"
        )

    return "\n\n".join(transcript)

def count_message_tokens(messages, summary: str) -> int:
    """
        估算当前上下文 Token 数量。
        """
    total_tokens = 0
    for m in messages:
        content = getattr(m, "content", "")
        if isinstance(content, list):  # 多模态内容块
            content = "".join(
                b.get("text", "") for b in content if isinstance(b, dict)
            )
        total_tokens += llm.get_num_tokens(str(content))
        # 工具调用参数也要算，否则带 tool_calls 的消息会被低估
        tool_calls = getattr(m, "tool_calls", None) or []
        for tc in tool_calls:
            total_tokens += llm.get_num_tokens(str(tc.get("args", "")))
    if summary:
        total_tokens += llm.get_num_tokens(summary)
    return total_tokens

async def memory_compression_node(state):

    messages = state.get("messages", [])
    previous_summary = state.get("summary", "")

    #  检查上下文 Token 数量
    token_count = count_message_tokens(
        messages,
        previous_summary
    )

    #  未达到阈值，直接跳过
    if token_count < 20_000:
        return {"summary": previous_summary}

    # 1. 获取可安全压缩的历史消息
    messages_to_compress = select_messages_to_compress(messages)

    if not messages_to_compress:
        return {}

    # 2. 转换为文本
    transcript = messages_to_text(messages_to_compress)

    # 3. 使用已有摘要 + 新增对话进行增量压缩
    SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
        ("system",
         "你在为一个金融对话助理压缩记忆。把【已有摘要】和【新增对话】合并成"
         "一段不超过 400 字的中文摘要，必须保留：\n"
         "1) 用户的身份背景与投资目标；\n"
         "2) 出现过的产品代码、金额、买卖方向；\n"
         "3) 已经得出的合规结论与人工审批结果（通过 / 被拒 / 待批）；\n"
         "4) 尚未完成的待办（比如“用户还要确认金额”）。\n"
         "不要编造未出现的信息，不要保留寒暄与重复表述，不要输出 Markdown。"
         "只输出摘要正文。"),
        ("human", "【已有摘要】\n{previous}\n\n【新增对话】\n{transcript}"),
    ])

    chain = SUMMARY_PROMPT | llm

    response = await chain.ainvoke({
        "previous": previous_summary,
        "transcript": transcript
    })

    new_summary = response.content.strip()

    # 4. 删除已经完成压缩的历史消息
    remove_messages = [
        RemoveMessage(id=msg.id)
        for msg in messages_to_compress
        if msg.id is not None
    ]

    return {
        "summary": new_summary,
        "messages": remove_messages
    }