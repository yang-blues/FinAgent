import logging

from langchain_core.runnables import Runnable, RunnableConfig

logger = logging.getLogger(__name__)
class FinAssistant:
    """图里的一个”助理节点“工厂"""
    def __init__(self,runnable:Runnable,max_empty_retries :int = 2):
        """
        初始化助理节点。

        :param runnable: prompt 与工具绑定后得到的 Runnable。
        """
        self.runnable = runnable
        self.max_empty_retries = max_empty_retries

    @staticmethod
    def _has_valid_content(content) -> bool:
        """判断模型是否生成了有效文本"""
        if isinstance(content,str):
            return bool(content.strip())

        if isinstance(content,list):
            return any(
                isinstance(block,dict)
                and bool(str(block.get("text","")).strip())
                for block in content
            )
        return False

    async def __call__(self,state:dict,config:RunnableConfig):
        """
        执行本节点。

        这里套一层重试：大模型偶尔会返回空内容且不带工具调用，
        这种"空转"会让图卡住。补一句提示让它重新输出，而不是直接崩。

        :param state: 当前图状态。
        :param config: 运行配置，里面有 thread_id / user_id。
        :return: 只包含 messages 的状态增量。
        """
        messages = list(state["messages"])

        for attempt in range(self.max_empty_retries + 1):

            result = await self.runnable.ainvoke(
                {**state, "messages": messages},
                config=config,
            )

            # 有工具调用，或者有有效文本，均视为有效输出
            if result.tool_calls or self._has_valid_content(
                    result.content
            ):
                return {"messages": result}

            logger.warning(
                "模型返回无效输出 | 尝试次数=%s",
                attempt + 1,
            )

            if attempt >= self.max_empty_retries:
                raise RuntimeError(
                    "模型连续返回无效输出，已达到最大重试次数"
                )
            #修正提示只在当前节点内部使用，不会被持久化到对话历史。
            messages.append(
                ("user", "请提供一个真实的输出作为回应")
            )
