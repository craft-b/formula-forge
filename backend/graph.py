import re
from typing import Literal, Optional, TypedDict, List

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from llm import get_llm
from json_utils import extract_json_block

llm = get_llm()
# Formula generation uses Groq JSON mode so the model must emit a single JSON
# object (structured-output enforcement, F2/F13). RAG answers use plain `llm`.
formula_llm = llm.bind(response_format={"type": "json_object"})

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


class AgentState(TypedDict, total=False):
    messages: List
    # Explicit routing override from the UI ("formulate"). The brief-builder's
    # "Generate verified formula" CTA must never fall through to Q&A because
    # the intent regex didn't match the user's phrasing.
    intent: Optional[str]


def detect_intent(message: str) -> Literal["formulate", "search"]:
    """Return routing intent for a user message.

    Uses regex rather than an LLM call deliberately: routing is a deterministic
    pattern-match problem, and adding an LLM hop here would cost ~300ms and one
    extra API call on every single message. The regex covers conjugations and
    natural variants the old substring list missed (see _FORMULATION_RE above).
    """
    return "formulate" if _FORMULATION_RE.search(message) else "search"


# Maps a dietary-constraint module to the phrases that activate it. Keyword-based
# by design (same rationale as detect_intent): deterministic and zero-latency.
_MODULE_PATTERNS: dict[str, re.Pattern] = {
    "renal": re.compile(r"\b(renal|kidney|ckd|dialysis|low[\s-]?phosphorus|low[\s-]?potassium|low[\s-]?sodium)\b", re.I),
    "diabetic": re.compile(r"\b(diabet\w*|low[\s-]?glyc-?emic|low[\s-]?sugar|sugar[\s-]?free|no[\s-]?sugar|reduced[\s-]?sugar)\b", re.I),
    "high_protein": re.compile(r"\b(high[\s-]?protein|protein[\s-]?(enriched|fortified|packed)|added protein)\b", re.I),
    "low_fat": re.compile(r"\b(low[\s-]?fat|reduced[\s-]?fat|fat[\s-]?free|non[\s-]?fat)\b", re.I),
    "vegan": re.compile(r"\b(vegan|dairy[\s-]?free|plant[\s-]?based|non[\s-]?dairy)\b", re.I),
    "dysphagia_iddsi": re.compile(r"\b(dysphagia|iddsi|thickened|texture[\s-]?modified|swallow\w*)\b", re.I),
}


def detect_modules(message: str) -> list[str]:
    """Detect active dietary-constraint modules from a user message.

    Returns the module ids whose activation phrases appear in the message, in a
    stable order. These drive the validation gate's compliance checks — they do
    not put constraint logic into any LLM prompt (that lives in declarative
    rulesets under domain/constraints/).
    """
    return [mod for mod, pat in _MODULE_PATTERNS.items() if pat.search(message)]


# Delta/modification phrasing for follow-up requests. Only consulted when the
# session already has a formula, so a false positive just means "treat this as a
# tweak to the existing formula" — a safe default that fixes the F7 dead-end.
_ITERATION_RE = re.compile(
    r"\b(?:instead|without|dairy[\s-]?free|make it|now\s+(?:make|do|try)|"
    r"reduce|lower|increase|raise|bump|more|less|fewer|swap|replace|substitute|"
    r"hold|keep|remove|drop|cut|add|higher|thinner|creamier|softer|firmer|"
    r"sweeter|richer|leaner|version)\b",
    re.I,
)


def detect_iteration(message: str) -> bool:
    """True if the message reads as a modification of an existing formula."""
    return bool(_ITERATION_RE.search(message))


_WORD_RE = re.compile(r"[a-z0-9]+")


def _ingredient_context_line(ing) -> str:
    """Format a governed ingredient with its real per-100 g nutrients for RAG."""
    nv = ing.nutrients_per_100g
    return (
        f"{ing.name}: {round(nv.energy_kcal)} kcal, {nv.protein_g}g protein, "
        f"{nv.fat_g}g fat, {nv.carbs_g}g carbs, sugars {nv.sugars_g}g, "
        f"P {round(nv.phosphorus_mg)}mg, K {round(nv.potassium_mg)}mg, "
        f"Na {round(nv.sodium_mg)}mg (per 100 g)"
    )


def search_foods(query: str, n: int = 8) -> List[str]:
    """Retrieve governed ingredients matching the query, with real nutrients.

    Retrieval now runs over the governed ingredient library (which carries full
    USDA-sourced nutrient vectors) rather than the old names-only usda_foods.json,
    so RAG answers are grounded in real numbers. Keyword scoring with
    word-boundary tokenization (so "milk" no longer matches "buttermilk") and a
    length filter; the library is already deduplicated (F8). Vector search is the
    Phase B upgrade (spec §2.2) once a managed store replaces the free tier.
    """
    tokens = {w for w in _WORD_RE.findall(query.lower()) if len(w) > 2}
    if not tokens:
        return []
    from domain import get_repository
    scored = []
    for ing in get_repository().ingredients:
        haystack = set(_WORD_RE.findall(f"{ing.name} {ing.role}".lower()))
        score = len(tokens & haystack)
        if score > 0:
            scored.append((score, ing))
    scored.sort(key=lambda pair: (-pair[0], pair[1].name))
    return [_ingredient_context_line(ing) for _, ing in scored[:n]]


def orchestrator(state: AgentState):
    return {"messages": state["messages"]}


def route(state: AgentState) -> Literal["formula_agent", "rag_agent"]:
    if state.get("intent") == "formulate":
        return "formula_agent"
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


_FORMULA_SYSTEM = SystemMessage(content="""You are FormulaForge, an expert frozen-dessert \
formulation AI for medical and institutional nutrition. Generate realistic, \
scientifically-grounded ice cream / frozen-dessert formulas.

You do NOT report nutrition numbers — the system computes all nutrition from a \
governed ingredient database. Propose only the ingredient structure.

Respond with ONLY a single valid JSON object.""")


def _allowed_ingredient_lines() -> str:
    """Bulleted list of the governed ingredient names the model may choose from.

    Constraining generation to the library (rather than letting the LLM invent
    ingredients) is what makes every proposal resolvable and therefore
    verifiable. Imported lazily to keep graph import light.
    """
    from domain import get_repository
    return "\n".join(f"- {ing.name}" for ing in get_repository().ingredients)


def build_formula_messages(
    user_message: str, feedback: Optional[str] = None, parent: Optional[str] = None
) -> list:
    """Build the formula-generation prompt.

    Deliberately omits conversation history: formula generation needs a clean,
    tightly-constrained prompt. Nutrition fields are intentionally absent from
    the requested schema — the domain layer computes them.

    When `parent` is given (iteration), the current formula is shown and the
    user's message is treated as a delta to apply — this is what lets follow-ups
    like "now make it dairy-free" modify the existing formula instead of
    generating from nothing (F7).
    """
    allowed = _allowed_ingredient_lines()
    task = f"Create a frozen-dessert formula for: {user_message}"
    if parent:
        task = (
            f"Modify the CURRENT FORMULA below as requested.\n"
            f"CURRENT FORMULA:\n{parent}\n\n"
            f"REQUESTED CHANGE: {user_message}\n"
            f"Keep everything else as close to the current formula as possible."
        )
    repair = ""
    if feedback:
        repair = (
            "\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED. Fix these problems and try "
            f"again:\n{feedback}\n"
        )
    prompt = HumanMessage(content=f"""{task}

Choose ingredients ONLY from this governed list (use the names verbatim):
{allowed}

Return ONLY this JSON structure:
{{
  "type": "formula",
  "product_name": "...",
  "description": "...",
  "product_format": "premium | standard | soft_serve | gelato | novelty",
  "overrun_pct": null,
  "ingredients": [
    {{"ref": "<exact name from the list>", "percentage": 0.0, "notes": "..."}}
  ],
  "formulation_notes": "..."
}}

Requirements:
- Ingredient percentages must sum to 100.
- Use 4-8 ingredients chosen only from the list above.
- Do NOT include any nutrition fields — the system computes nutrition.
- Formulation notes should cover processing, texture, or regulatory considerations.{repair}""")
    return [_FORMULA_SYSTEM, prompt]


def _invoke_formula(messages: list) -> str:
    """Call the JSON-mode LLM and return the extracted JSON string."""
    response = formula_llm.invoke(messages)
    return extract_json_block(response.content)


def regenerate_formula(user_message: str, feedback: str) -> str:
    """One repair re-prompt: regenerate a formula given validation feedback.

    Called by the API layer when the first attempt cannot be resolved/validated
    into a usable formula. Returns raw JSON (still validated downstream).
    """
    return _invoke_formula(build_formula_messages(user_message, feedback=feedback))


def iterate_formula(user_message: str, parent: str, feedback: Optional[str] = None) -> str:
    """Generate a modified formula from a parent formula and a delta request."""
    return _invoke_formula(
        build_formula_messages(user_message, feedback=feedback, parent=parent))


def formula_agent(state: AgentState):
    """Generate a structured frozen-dessert formula as a JSON object.

    Uses Groq JSON mode and a library-constrained ingredient list so the output
    reliably parses and resolves. main.py runs the domain validation gate on
    this output (and may trigger exactly one repair via regenerate_formula).
    """
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    user_message = user_messages[-1].content
    raw = _invoke_formula(build_formula_messages(user_message))
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
