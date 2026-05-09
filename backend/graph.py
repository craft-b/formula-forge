import chromadb
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
from typing import TypedDict, List

# Load ChromaDB
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="usda_foods")

class AgentState(TypedDict):
    messages: List

def orchestrator(state: AgentState):
    last_message = state["messages"][-1].content
    return {"messages": state["messages"] + [
        AIMessage(content=f"Looking up: {last_message}")
    ]}

def rag_agent(state: AgentState):
    # Get the original user question
    user_message = state["messages"][0].content
    
    # Query ChromaDB
    results = collection.query(
        query_texts=[user_message],
        n_results=5
    )
    
    # Format results
    foods = results["documents"][0]
    if foods:
        response = "Here are related foods from USDA FoodData:\n" + "\n".join(f"• {f}" for f in foods)
    else:
        response = "No matching foods found."
    
    return {"messages": state["messages"] + [
        AIMessage(content=response)
    ]}

def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("orchestrator", orchestrator)
    graph.add_node("rag_agent", rag_agent)
    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", "rag_agent")
    graph.add_edge("rag_agent", END)
    return graph.compile()

agent = build_graph()