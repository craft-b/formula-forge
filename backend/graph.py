import chromadb
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from llm import get_llm
from typing import TypedDict, List

# Load ChromaDB
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="usda_foods")

# Load LLM via swap layer
llm = get_llm()

class AgentState(TypedDict):
    messages: List

def orchestrator(state: AgentState):
    return {"messages": state["messages"]}

def rag_agent(state: AgentState):
    user_message = state["messages"][0].content

    # Query ChromaDB
    results = collection.query(
        query_texts=[user_message],
        n_results=5
    )
    foods = results["documents"][0]
    context = "\n".join(f"- {f}" for f in foods)

    # Build prompt
    system = SystemMessage(content="""You are FormulaForge, an AI food formulation assistant.
You help food scientists, chefs, and product developers with ingredient selection,
nutrition analysis, and recipe formulation. Be concise, specific, and practical.""")

    prompt = HumanMessage(content=f"""User question: {user_message}

Relevant USDA foods found:
{context}

Based on these ingredients, provide a helpful, specific answer.""")

    response = llm.invoke([system, prompt])

    return {"messages": state["messages"] + [
        AIMessage(content=response.content)
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