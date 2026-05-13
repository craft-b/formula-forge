import json
import os
from typing import Literal, TypedDict, List

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from llm import get_llm

json_path = os.path.join(os.path.dirname(__file__), "usda_foods.json")
with open(json_path, "r") as f:
    FOODS = json.load(f)

llm = get_llm()

FORMULATION_TRIGGERS = [
    "create a formula", "create formula", "formulate a", "formulate an",
    "build a formula", "build a recipe", "make a formula", "make a recipe",
    "generate a formula", "design a formula", "develop a formula",
    "create a product", "make a product", "new formula", "formula for",
    "recipe for", "i need a formula", "can you formulate",
]


class AgentState(TypedDict):
    messages: List


def detect_intent(message: str) -> Literal["formulate", "search"]:
    msg = message.lower()
    for trigger in FORMULATION_TRIGGERS:
        if trigger in msg:
            return "formulate"
    return "search"


def search_foods(query: str, n: int = 8) -> List[str]:
    query_words = [w for w in query.lower().split() if len(w) > 2]
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


def route(state: AgentState) -> Literal["formula_agent", "rag_agent"]:
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if user_messages:
        return "formula_agent" if detect_intent(user_messages[-1].content) == "formulate" else "rag_agent"
    return "rag_agent"


def rag_agent(state: AgentState):
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    user_message = user_messages[-1].content
    foods = search_foods(user_message)
    context = "\n".join(f"- {f}" for f in foods) if foods else "No matching foods found in USDA database."

    system = SystemMessage(content="""You are FormulaForge, an AI food formulation assistant.
You help food scientists, chefs, and product developers with ingredient selection,
nutrition analysis, and recipe formulation. Be concise, specific, and practical.
Reference conversation history when relevant.""")

    # Include last 10 messages so the LLM sees conversation context
    history = state["messages"][-10:]
    context_note = SystemMessage(content=f"Relevant USDA foods for this query:\n{context}")

    response = llm.invoke([system, context_note] + history)
    return {"messages": state["messages"] + [AIMessage(content=response.content)]}


def formula_agent(state: AgentState):
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    user_message = user_messages[-1].content
    foods = search_foods(user_message, n=10)
    context = "\n".join(f"- {f}" for f in foods) if foods else "No specific USDA matches — use general food science knowledge."

    system = SystemMessage(content="""You are FormulaForge, an expert food formulation AI.
Generate realistic, scientifically-grounded food formulas.
Respond with ONLY a valid JSON object — no markdown, no explanation, no code fences.""")

    prompt = HumanMessage(content=f"""Create a detailed food formula for: {user_message}

Relevant USDA ingredients:
{context}

Return ONLY this JSON structure with no extra text:
{{
  "type": "formula",
  "product_name": "...",
  "description": "...",
  "ingredients": [
    {{"name": "...", "percentage": 0.0, "notes": "..."}}
  ],
  "nutrition_per_100g": {{
    "calories": 0,
    "protein": 0.0,
    "fat": 0.0,
    "carbs": 0.0
  }},
  "formulation_notes": "..."
}}

Requirements:
- Ingredients must sum to exactly 100%
- Include 4-8 ingredients with realistic percentages
- Nutrition values must be realistic estimates
- Formulation notes should cover processing, shelf life, or regulatory considerations""")

    response = llm.invoke([system, prompt])

    # Strip markdown fences if the LLM added them anyway
    raw = response.content.strip()
    if "```" in raw:
        for block in raw.split("```"):
            cleaned = block.lstrip("json").strip()
            if cleaned.startswith("{"):
                raw = cleaned
                break

    return {"messages": state["messages"] + [AIMessage(content=raw)]}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("orchestrator", orchestrator)
    graph.add_node("rag_agent", rag_agent)
    graph.add_node("formula_agent", formula_agent)
    graph.set_entry_point("orchestrator")
    graph.add_conditional_edges("orchestrator", route)
    graph.add_edge("rag_agent", END)
    graph.add_edge("formula_agent", END)
    return graph.compile()


agent = build_graph()
