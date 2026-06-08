
from pprint import pprint
from perplexity import Perplexity

from ddgs import DDGS

# # with DDGS() as ddgs:
# #     pprint([r for r in ddgs.text("CHATGPT", region='cn-zh', max_results=10)])
# with DDGS() as ddgs:
#     context = ddgs.text("CHATGPT", region='cn-zh', max_results=10)
#     print(context)
#
# client = Perplexity(
#     api_key="perplexity-dev-3uKXKr-k4jkw67HcZHsjDlMxqXGK0zG3MqZKRJMLjFaqEH5jz"
# )
#
# search = client.search.create(
#     query="latest AI developments 2024",
#     max_results=5,
#     max_tokens_per_page=4096
# )
#
# for result in search.results:
#     print(f"{result.title}: {result.url}")
#
# from langchain_community.utilities import SearxSearchWrapper
#
# s = SearxSearchWrapper(searx_host="http://localhost:8888")  # 使用API代理服务提高访问稳定性
# print(s.run("what is a large language model?"))


import redis   # 导入redis 模块



r = redis.Redis( connection_pool=pool,host='127.0.0.1', port=6379, db=0 , password="123456", decode_responses=True,)


# r.set('name', 'runoob' ,  )  # 设置 name 对应的值
# print(r['name'])
# print(r.get('name'))  # 取出键 name 对应的值
# print(type(r.get('name')))  # 查看类型



import redis
import json

# 连接本地 Redis
client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

queue_name = 'my_light_queue'

def send_message(data):
    # 将数据推入队列左侧
    client.lpush(queue_name, json.dumps(data))
    print(f"已发送数据: {data}")

# 发送测试数据
if __name__ == '__main__':
    message = {"action": "update", "task_id": 1001, "content": "hello world"}
    send_message(message)

import redis
import json
import time

client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
queue_name = 'my_light_queue'
def receive_messages():
    print("开始监听队列...")
    while True:
        # BRPOP 是阻塞式读取，0 表示无限期等待，直到有新数据进入
        # 返回元组结构：(队列名, 实际数据)
        _, data_str = client.brpop(queue_name, timeout=0)
        # 解析数据
        data = json.loads(data_str)
        print(f"收到数据: {data}")
        # 执行你的轻量级处理逻辑
        time.sleep(1)
if __name__ == '__main__':
    receive_messages()











