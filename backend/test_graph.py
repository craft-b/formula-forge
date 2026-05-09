from langchain_core.messages import HumanMessage
from graph import agent

result = agent.invoke({
    "messages": [HumanMessage(content="high protein beef")]
})

print(result["messages"][-1].content)