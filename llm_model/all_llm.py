"""创建主模型和备用模型实例"""
from langchain_openai import ChatOpenAI

from untils.env_utils import QWEN_API_KEY, QWEN_BASE_URL

llm = ChatOpenAI(
    model='qwen3.8-max-0902',
    api_key=QWEN_API_KEY,
    base_url=QWEN_BASE_URL,
    timeout=60,#单次模型请求最多等待60秒(两次收到数据之间的最大空闲间隔不能超过 60s)
    max_retries=0,#关闭底层SDK自动重试
)

# res = llm.invoke('你好')
# print(res)

