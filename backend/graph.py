import json
import os
import re
from typing import Literal, TypedDict, List

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from llm import get_llm

json_path = os.path.join(os.path.dirname(__file__), "usda_foods.json")
with open(json_path, "r") as f:
    FOODS = json.load(f)

llm = get_llm()

# Compiled once at import time. Matches formulation intent across verb conjugations
# and natural phrasing variants that the old substring list missed, e.g.:
#   "let me formulate", "I need you to formulate a shake",
#   "build me an oncology formula", "can we develop a new recipe for..."
_FORMULATION_RE = re.compile(
    r"\b(?:"
    r"formulate[sd]?|formulating"
    r"|(?:create|build|make|generate|design|develop|draft)\s+(?:me\s+)?an?(?:\s+[\w-]+){0,4}\s+(?:formula|formulation|recipe|product)"
    r"|new\s+(?:formula|formulation|recipe)"
    r"|(?:formula|recipe)\s+for\b"
    r"|i\s+need\s+a\s+formula"
    r")",
    re.IGNORECASE,
)


class AgentState(TypedDict):
    messages: List


def detect_intent(message: str) -> Literal["formulate", "search"]:
    """Return routing intent for a user message.

    Uses regex rather than an LLM call deliberately: routing is a deterministic
    pattern-match problem, and adding an LLM hop here would cost ~300ms and one
    extra API call on every single message. The regex covers conjugations and
    natural variants the old substring list missed (see _FORMULATION_RE above).
    """
    return "formulate" if _FORMULATION_RE.search(message) else "search"


def search_foods(query: str, n: int = 8) -> List[str]:
    """Score USDA foods by keyword overlap with the query and return the top n.

    Chosen over vector embeddings because Render's free tier cannot run an
    ONNX embedding model — the cold-start memory spike killed the service.
    Known limitations: no stemming ("proteins" won't match "protein"), no
    bigram matching, no field weighting. Good enough for the 1,000-food
    Foundation Foods dataset where descriptions are short and specific.
    """
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
    """Handle ingredient and nutrition questions with USDA context + conversation history.

    Passes the last 10 messages to the LLM so follow-up questions ("what about
    the sodium content?") resolve correctly. The window is capped at 10 to stay
    within Groq's context limits and avoid paying for tokens from very old turns
    that are unlikely to be relevant.
    """
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
    """Generate a structured food formula as a JSON object.

    Deliberately does not pass conversation history to the LLM. Formula
    generation needs a clean, tightly-constrained prompt to reliably produce
    valid JSON — injecting multi-turn history increases the chance the model
    breaks the JSON contract or mixes in prior context. The tradeoff is that
    follow-up reformulation requests ("now make it dairy-free") require the
    user to re-state the base product; this is acceptable for the current scope.

    The JSON schema is enforced by the prompt. main.py parses and validates
    the output so graph.py stays stateless and the API response is always typed.
    """
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
    """Compile and return the LangGraph agent.

    Graph topology: orchestrator → [route] → formula_agent | rag_agent → END.
    The orchestrator node is a deliberate pass-through reserved for future
    input preprocessing (e.g., PII scrubbing, rate-limit checks at graph level)
    without needing to rewire the conditional edge. compile() freezes the graph
    so it can be invoked concurrently without shared mutable state.
    """
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
