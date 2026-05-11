from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from llm import get_llm
from typing import TypedDict, List
import json
import os

# Load USDA data directly into memory
json_path = os.path.join(os.path.dirname(__file__), "usda_foods.json")
with open(json_path, "r") as f:
    FOODS = json.load(f)

llm = get_llm()

class AgentState(TypedDict):
    messages: List

def search_foods(query: str, n: int = 5) -> List[str]:
    query_words = query.lower().split()
    scored = []
    for food in FOODS:
        desc = food["description"].lower()
        score = sum(1 for word in query_words if word in desc)
        if score > 0:
            scored.append((score, food["description"]))
    scored.sort(reverse=True)
    return [desc for _, desc in scored[:n]]

def orchestrator(state: AgentState):
    return {"messages": state["messages"]}

def rag_agent(state: AgentState):
    user_message = state["messages"][0].content
    foods = search_foods(user_message)
    
    if not foods:
        context = "No matching foods found in USDA database."
    else:
        context = "\n".join(f"- {f}" for f in foods)

    system = SystemMessage(content="""You are FormulaForge, an AI food formulation assistant.
You help food scientists, chefs, and product developers with ingredient selection,
nutrition analysis, and recipe formulation. Be concise, specific, and practical.""")

    prompt = HumanMessage(content=f"""User question: {user_message}

Relevant USDA foods found:
{context}

Based on these ingredients, provide a helpful, specific answer.""")

    response = llm.invoke([system, prompt])
    return {"messages": state["messages"] + [AIMessage(content=response.content)]}

def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("orchestrator", orchestrator)
    graph.add_node("rag_agent", rag_agent)
    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", "rag_agent")
    graph.add_edge("rag_agent", END)
    return graph.compile()

agent = build_graph()