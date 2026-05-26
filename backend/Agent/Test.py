
from pprint import pprint
from perplexity import Perplexity

from ddgs import DDGS

# with DDGS() as ddgs:
#     pprint([r for r in ddgs.text("CHATGPT", region='cn-zh', max_results=10)])
with DDGS() as ddgs:
    context = ddgs.text("CHATGPT", region='cn-zh', max_results=10)
    print(context)

client = Perplexity(
    api_key="perplexity-dev-3uKXKr-k4jkw67HcZHsjDlMxqXGK0zG3MqZKRJMLjFaqEH5jz"
)

search = client.search.create(
    query="latest AI developments 2024",
    max_results=5,
    max_tokens_per_page=4096
)

for result in search.results:
    print(f"{result.title}: {result.url}")

from langchain_community.utilities import SearxSearchWrapper

s = SearxSearchWrapper(searx_host="http://localhost:8888")  # 使用API代理服务提高访问稳定性
print(s.run("what is a large language model?"))
