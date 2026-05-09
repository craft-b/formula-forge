from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
from typing import TypedDict, List

class AgentState(TypedDict):
    messages: List

def orchestrator(state: AgentState):
    last_message = state["messages"][-1].content
    return {"messages": state["messages"] + [
        AIMessage(content=f"Orchestrator received: {last_message}")
    ]}

def echo_agent(state: AgentState):
    last_message = state["messages"][-1].content
    return {"messages": state["messages"] + [
        AIMessage(content=f"Echo Agent says: {last_message}")
    ]}

def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("orchestrator", orchestrator)
    graph.add_node("echo_agent", echo_agent)
    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", "echo_agent")
    graph.add_edge("echo_agent", END)
    return graph.compile()

agent = build_graph()