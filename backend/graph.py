import logging
import re
from typing import Literal, Optional, TypedDict, List

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from llm import get_llm
from json_utils import extract_json_block

logger = logging.getLogger(__name__)

llm = get_llm()
# Formula generation uses Groq JSON mode so the model must emit a single JSON
# object (structured-output enforcement, F2/F13). RAG answers use plain `llm`.
formula_llm = llm.bind(response_format={"type": "json_object"})

# Compiled once at import time. Matches formulation intent across verb conjugations
# and natural phrasing variants that the old substring list missed, e.g.:
#   "let me formulate", "I need you to formulate a shake",
#   "build me an oncology formula", "can we develop a new recipe for..."
# What this application actually makes. The pattern used to accept only
# "formula | formulation | recipe | product", so "build me a frozen dessert" and
# "create a chocolate ice cream" — the two most natural ways to ask for the
# product — routed to Q&A instead of generation (eval finding F-E1).
_PRODUCT_NOUN = (
    r"(?:formulations?|formulas?|recipes?|products?|desserts?"
    r"|ice\s*creams?|gelatos?|sorbets?|sherbets?|soft[\s-]?serves?)"
)

_FORMULATION_RE = re.compile(
    r"\b(?:"
    r"formulate[sd]?|formulating"
    # A verb, up to four words of description, then the thing itself.
    r"|(?:create|build|make|generate|design|develop|draft|need|want)"
    r"\s+(?:me\s+)?(?:an?|some)?(?:\s+[\w-]+){0,4}\s+" + _PRODUCT_NOUN +
    r"|new\s+" + _PRODUCT_NOUN +
    r"|" + _PRODUCT_NOUN + r"\s+for\b"
    r")",
    re.IGNORECASE,
)

# Bare noun, no verb: operators type "renal formula" and "vegan formula
# please". Restricted to the unambiguous nouns — a bare "dessert" turns up in
# plenty of questions. It used to sit inside _FORMULATION_RE and so fired on
# questions too, and after a first formula the natural follow-up is a question
# about "this formula": "why does this formula use more cream?" was sent to the
# formulator and came back as a new formula. detect_intent now applies it only
# to messages that are not phrased as questions.
_BARE_FORMULA_RE = re.compile(r"\b(?:formulations?|formulas?)\b", re.IGNORECASE)


class AgentState(TypedDict, total=False):
    messages: List
    # Explicit routing override from the UI ("formulate"). The brief-builder's
    # "Generate verified formula" CTA must never fall through to Q&A because
    # the intent regex didn't match the user's phrasing.
    intent: Optional[str]
    # Active dietary-constraint module ids — rendered into the formula prompt
    # as design targets so proposals aim at the limits the gate will enforce.
    modules: Optional[List[str]]
    # The governed rows the RAG answer was given. main.py checks every figure in
    # the answer against these (grounding.py) and tells the UI which were not.
    context: Optional[List[str]]


# A bare product noun anywhere in the message, and the shapes a question takes.
# "gelato" on its own is ambiguous — it appears in briefs and in questions alike
# — so neither of these decides anything by itself; see detect_intent.
_PRODUCT_NOUN_RE = re.compile(r"\b" + _PRODUCT_NOUN + r"\b", re.IGNORECASE)
_QUESTION_RE = re.compile(
    r"(?:\?)|^\s*(?:what|which|how|why|when|who|whose|is|are|was|were|do|does|did"
    r"|can|could|should|would|will|explain|describe|define|compare|tell\s+me"
    r"|give\s+me\s+an?\s+(?:overview|explanation)|help\s+me\s+understand)\b",
    re.IGNORECASE,
)


def detect_intent(message: str) -> Literal["formulate", "search"]:
    """Return routing intent for a user message.

    Uses regex rather than an LLM call deliberately: routing is a deterministic
    pattern-match problem, and adding an LLM hop here would cost ~300ms and one
    extra API call on every single message. The regex covers conjugations and
    natural variants the old substring list missed (see _FORMULATION_RE above).

    Second rule, for the terse phrasing operators actually type. _FORMULATION_RE
    needs a verb ("make me a gelato") or one of the two unambiguous nouns
    ("renal formula"). It does not fire on "renal gelato", "vegan sorbet",
    "diabetic ice cream" or "dysphagia ice cream" — a constraint qualifier next
    to the product, which is a brief and not a question by any reading. Those
    routed to Q&A, and the eval's own notes call that the dangerous direction:
    the ruleset never runs, so the formula is validated against nothing and comes
    back looking clean.

    A bare product noun cannot decide this on its own, because it turns up in
    plenty of questions ("what is a gelato?", "why is my soft serve icy?"). The
    disambiguator is a clinical constraint sitting beside it: nobody asks this
    system a general-knowledge question about a renal gelato. So the message must
    name a product, activate at least one constraint module, and not be phrased
    as a question.
    """
    if _FORMULATION_RE.search(message):
        return "formulate"
    if _BARE_FORMULA_RE.search(message) and not _QUESTION_RE.search(message):
        return "formulate"
    if (_PRODUCT_NOUN_RE.search(message)
            and detect_modules(message)
            and not _QUESTION_RE.search(message)):
        return "formulate"
    return "search"


# Maps a dietary-constraint module to the phrases that activate it. Keyword-based
# by design (same rationale as detect_intent): deterministic and zero-latency.
# Three failure modes these patterns must avoid, each found by the live eval:
#
#   Under-firing is the dangerous one (F-E3). A missed module means the ruleset
#   never runs, the formula validates against nothing, and it passes looking
#   clean — no error anywhere. `\bdialysis\b` cannot match inside
#   "hemodialysis"; `\bdiabet\w*` cannot match inside "prediabetic". Both are
#   ordinary clinical words, so those stems now allow a leading prefix.
#
#   Over-firing on an ingredient name (F-E2). `non[\s-]?fat` fired on the
#   ingredient "nonfat dry milk", imposing a low-fat clinical ceiling nobody
#   asked for. A lookahead excludes the dairy-ingredient sense.
#
#   Missing the vocabulary entirely (F-E4). "nephrology", "blood glucose" and a
#   numeric protein target carry unambiguous clinical intent and matched
#   nothing at all.
_MODULE_PATTERNS: dict[str, re.Pattern] = {
    "renal": re.compile(
        r"\b(renal|kidney|ckd|esrd|nephrolog\w*|end[\s-]?stage\s+renal"
        r"|[a-z]*dialysis"
        r"|low[\s-]?phosphorus|low[\s-]?potassium|low[\s-]?sodium)\b", re.I),
    "diabetic": re.compile(
        # glyca?emic covers both spellings: "glycemic" and "glycaemic". A
        # character class of [ae] does not — the British form has both letters.
        r"\b((?:pre)?diabet\w*|low[\s-]?glyc-?a?emic|glyca?emic\s+(?:index|load)"
        r"|blood\s+(?:glucose|sugar)|low[\s-]?sugar|sugar[\s-]?free"
        r"|no[\s-]?sugar|reduced[\s-]?sugar)\b", re.I),
    "high_protein": re.compile(
        r"\b(high[\s-]?protein|protein[\s-]?(enriched|fortified|packed)"
        r"|added protein|\d+\s*g(?:rams?)?\s+(?:of\s+)?protein)\b", re.I),
    "low_fat": re.compile(
        r"\b(low[\s-]?fat|reduced[\s-]?fat|fat[\s-]?free"
        r"|non[\s-]?fat(?!\s+(?:dry\s+)?milk))\b", re.I),
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


# A request phrased as a question is still a request: "can you make it
# sweeter?", "could we swap the cream?". So is a message that opens with the
# change itself ("swap the cream?"). Neither is a question about the formula.
_CHANGE_REQUEST_RE = re.compile(
    r"^\s*(?:please\s+|(?:can|could|would|will)\s+(?:you|we)\s+(?:please\s+)?)?"
    r"(?:now\s+)?(?:make|reduce|lower|increase|raise|bump|swap|replace|substitute"
    r"|hold|keep|remove|drop|cut|add|try|use)\b",
    re.I,
)


def detect_iteration(message: str) -> bool:
    """True if the message reads as a modification of an existing formula.

    The change vocabulary is broad on purpose (a false positive only means
    "treat this as a tweak"), which is exactly why questions need excluding:
    "why does this formula use more cream?" contains "more" and was rewritten
    into a new formula instead of being answered. A question-shaped message is
    an iteration only when it is a change request in question form.
    """
    if not _ITERATION_RE.search(message):
        return False
    if _QUESTION_RE.search(message) and not _CHANGE_REQUEST_RE.search(message):
        return False
    return True


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


# Words that carry no ingredient identity. "low" and "high" are the costly ones:
# "low-phosphorus protein" matched "Buttermilk, low fat" on "low" and ranked it
# first. They are read as an ordering instruction instead (_NUTRIENT_ORDER).
_SEARCH_STOPWORDS = frozenset("""
    about added amount and any are best between can compare content contain contains could
    does for from good has have high how into its less low lower lowest many more much need
    per reduce reduced rich serving should source than that the this use using want what
    which will with would your
""".split())

# Query words that name a functional role rather than an ingredient. "Which
# sweetener is best?" shares no word with "Erythritol" or "Allulose"; it shares
# a role with them.
_ROLE_TERMS: dict[str, frozenset[str]] = {
    "sweetener": frozenset({"sweetener", "polyol", "high_intensity"}),
    "sweeteners": frozenset({"sweetener", "polyol", "high_intensity"}),
    "sweetening": frozenset({"sweetener", "polyol", "high_intensity"}),
    "polyol": frozenset({"polyol"}), "polyols": frozenset({"polyol"}),
    "stabilizer": frozenset({"stabilizer"}), "stabilizers": frozenset({"stabilizer"}),
    "stabiliser": frozenset({"stabilizer"}), "stabilisers": frozenset({"stabilizer"}),
    "thickener": frozenset({"stabilizer"}), "thickeners": frozenset({"stabilizer"}),
    "emulsifier": frozenset({"emulsifier"}), "emulsifiers": frozenset({"emulsifier"}),
    "fiber": frozenset({"bulking_fiber", "mimetic"}), "fibre": frozenset({"bulking_fiber", "mimetic"}),
}

# "low phosphorus", "lowest sodium", "high protein": a direction and a field.
# Ties on relevance are broken by that nutrient, so the answer the question
# asked for comes first. A diabetic brief asks for low sugars.
_NUTRIENT_WORDS = {
    "phosphorus": "phosphorus_mg", "potassium": "potassium_mg", "sodium": "sodium_mg",
    "salt": "sodium_mg", "calcium": "calcium_mg", "sugar": "sugars_g", "sugars": "sugars_g",
    "fat": "fat_g", "protein": "protein_g", "calorie": "energy_kcal", "calories": "energy_kcal",
    "carb": "carbs_g", "carbs": "carbs_g", "fiber": "fiber_g", "fibre": "fiber_g",
}
_NUTRIENT_ORDER = re.compile(
    r"\b(low|lower|lowest|reduced|less|high|higher|highest|rich|more)[\s-]+(?:in\s+)?"
    r"(" + "|".join(_NUTRIENT_WORDS) + r")\b", re.I)
_DIRECTION = {"low": 1, "lower": 1, "lowest": 1, "reduced": 1, "less": 1,
              "high": -1, "higher": -1, "highest": -1, "rich": -1, "more": -1}


def _nutrient_order(query: str) -> Optional[tuple[str, int]]:
    """(field, +1 ascending | -1 descending) when the query asks for an extreme."""
    m = _NUTRIENT_ORDER.search(query)
    if m:
        return _NUTRIENT_WORDS[m.group(2).lower()], _DIRECTION[m.group(1).lower()]
    if re.search(r"\b(?:pre)?diabet\w*", query, re.I):
        return "sugars_g", 1
    return None


def search_foods(query: str, n: int = 8) -> List[str]:
    """Retrieve governed ingredients matching the query, with real nutrients.

    Retrieval runs over the governed ingredient library, so RAG answers are
    grounded in real numbers. Deterministic keyword scoring with word-boundary
    tokenization (so "milk" does not match "buttermilk"), plus three rules found
    by testing realistic questions (readiness review H8):

    * the product being made ("ice cream", "gelato", ...) is removed first —
      it describes the target, and "ice cream" matched every cream row;
    * role words ("sweetener", "stabilizer") match the ingredients in that
      role, which share no name word with the question;
    * "low/high <nutrient>" (and "diabetic", for sugars) orders equally
      relevant rows by that nutrient instead of alphabetically.

    Vector search is the Phase B upgrade (spec §2.2) once a managed store
    replaces the free tier.
    """
    text = _PRODUCT_NOUN_RE.sub(" ", query.lower())
    words = {w for w in _WORD_RE.findall(text) if len(w) > 2} - _SEARCH_STOPWORDS
    wanted_roles = set().union(*(_ROLE_TERMS.get(w, frozenset()) for w in words))
    # Role words are matched through wanted_roles. Nutrient words describe what
    # every row has, so they do not identify one ("potassium in whole milk") —
    # except the few that are also ingredient names ("whey protein", "salt").
    name_tokens = ((words - set(_ROLE_TERMS) - set(_NUTRIENT_WORDS))
                   | (words & {"protein", "fat", "salt", "sugar"}))
    if not name_tokens and not wanted_roles:
        return []
    order = _nutrient_order(query)
    from domain import get_repository
    scored = []
    for ing in get_repository().ingredients:
        haystack = set(_WORD_RE.findall(f"{ing.name} {ing.role.replace('_', ' ')}".lower()))
        score = len(name_tokens & haystack) + (2 if ing.role in wanted_roles else 0)
        if score > 0:
            scored.append((score, ing))

    def rank(pair):
        score, ing = pair
        value = getattr(ing.nutrients_per_100g, order[0]) * order[1] if order else 0
        return (-score, value, ing.name)

    scored.sort(key=rank)
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
    """Handle ingredient and nutrition questions with library context + conversation history.

    Passes the last 10 messages to the LLM so follow-up questions ("what about
    the sodium content?") resolve correctly. The window is capped at 10 to stay
    within Groq's context limits and avoid paying for tokens from very old turns
    that are unlikely to be relevant.
    """
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    user_message = user_messages[-1].content
    foods = search_foods(user_message)
    # Labelled as the governed library, not "USDA": the library mixes FDC rows
    # with curated ones, and the old label invited the model to cite USDA for
    # figures it had made up.
    context = ("\n".join(f"- {f}" for f in foods) if foods
               else "No matching ingredients in the governed library.")

    system = SystemMessage(content="""You are FormulaForge, an AI food formulation assistant.
You help food scientists, chefs, and product developers with ingredient selection,
nutrition analysis, and recipe formulation. Be concise, specific, and practical.
Reference conversation history when relevant.

Nutrient figures: state a number ONLY if it appears in the governed ingredient
rows provided below, and give it per 100 g as written there. If the question asks
about a nutrient or an ingredient those rows do not include, say plainly that it
is not in FormulaForge's governed library — do not supply a value from memory, do
not attribute a value to USDA or any other source, and do not compute daily-value
percentages. Every figure you write is checked against the rows, and any that do
not match are shown to the user as unverified.""")

    # Include last 10 messages so the LLM sees conversation context
    history = state["messages"][-10:]
    context_note = SystemMessage(
        content=f"Governed ingredient library rows for this query (per 100 g):\n{context}")

    response = llm.invoke([system, context_note] + history)
    return {"messages": state["messages"] + [AIMessage(content=response.content)],
            "context": foods}


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


def constraint_brief(modules: Optional[List[str]]) -> str:
    """Render the active rulesets' targets as design guidance for the prompt.

    The domain layer stays the only *evaluator* — this does not move constraint
    logic into prose. It renders the same versioned, declarative ruleset data
    the gate will enforce, so the model designs toward the limits instead of
    discovering them by rejection. Single source of truth is preserved: change
    a ruleset JSON and the prompt guidance changes with it.
    """
    if not modules:
        return ""
    from domain import get_ruleset
    lines: list[str] = []
    for mid in modules:
        rs = get_ruleset(mid)
        if not rs or rs.get("stub"):
            continue
        for lim in rs.get("nutrient_limits", []):
            basis = "per serving" if lim.get("basis", "per_serving") == "per_serving" else "per 100 g"
            field = lim["field"].replace("_", " ")
            if "max" in lim:
                lines.append(f"- {field} must be ≤ {lim['max']} {basis}. {lim['explanation']}")
            if "min" in lim:
                lines.append(f"- {field} must be ≥ {lim['min']} {basis}. {lim['explanation']}")
        for role in rs.get("ingredient_blacklist_roles", []):
            lines.append(f"- No ingredients with role '{role}' ({rs['label']}).")
        for allergen in rs.get("allergen_blacklist", []):
            lines.append(f"- No ingredients containing allergen '{allergen}' ({rs['label']}).")
    if not lines:
        return ""
    return (
        "\n\nACTIVE DIETARY CONSTRAINTS — the finished formula MUST satisfy every "
        "one of these. The system computes real nutrition from the ingredient "
        "database and will flag any violation, so choose ingredients and "
        "percentages that meet the limits:\n" + "\n".join(lines)
    )


def build_formula_messages(
    user_message: str,
    feedback: Optional[str] = None,
    parent: Optional[str] = None,
    modules: Optional[List[str]] = None,
) -> list:
    """Build the formula-generation prompt.

    Deliberately omits conversation history: formula generation needs a clean,
    tightly-constrained prompt. Nutrition fields are intentionally absent from
    the requested schema — the domain layer computes them.

    When `parent` is given (iteration), the current formula is shown and the
    user's message is treated as a delta to apply — this is what lets follow-ups
    like "now make it dairy-free" modify the existing formula instead of
    generating from nothing (F7).

    When `modules` is given, the active rulesets' numeric targets are rendered
    into the prompt (see constraint_brief) so the proposal is designed toward
    the limits the validation gate enforces.
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
    task += constraint_brief(modules)
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


def _json_mode_rejection(exc: Exception) -> Optional[str]:
    """The model's partial output if `exc` is a JSON-mode validation refusal.

    Groq validates JSON-mode output server-side and answers 400
    `json_validate_failed` when the model produced something unparseable. That
    is a malformed proposal, not a broken request - the same failure the repair
    path exists for - but raised as an exception it escaped the formula node and
    reached the user as "BadRequestError", skipping the one repair entirely.
    Returns None for any other error, which should propagate.
    """
    body = getattr(exc, "body", None)
    if not isinstance(body, dict):
        return None
    err = body.get("error", body)
    if not isinstance(err, dict) or err.get("code") != "json_validate_failed":
        return None
    return err.get("failed_generation") or ""


def _invoke_formula(messages: list) -> str:
    """Call the JSON-mode LLM and return the extracted JSON string.

    A provider-side JSON validation failure returns the partial generation
    (often empty) instead of raising, so it parses as a failed first attempt
    and takes the single repair like any other malformed proposal.
    """
    try:
        response = formula_llm.invoke(messages)
    except Exception as exc:
        partial = _json_mode_rejection(exc)
        if partial is None:
            raise
        logger.warning("Provider rejected JSON-mode output (json_validate_failed); "
                       "treating as an unparseable attempt")
        return extract_json_block(partial)
    return extract_json_block(response.content)


def regenerate_formula(user_message: str, feedback: str,
                       modules: Optional[List[str]] = None) -> str:
    """One repair re-prompt: regenerate a formula given validation feedback.

    Called by the API layer when the first attempt cannot be resolved/validated
    into a usable formula. Returns raw JSON (still validated downstream).
    """
    return _invoke_formula(
        build_formula_messages(user_message, feedback=feedback, modules=modules))


def iterate_formula(user_message: str, parent: str, feedback: Optional[str] = None,
                    modules: Optional[List[str]] = None) -> str:
    """Generate a modified formula from a parent formula and a delta request."""
    return _invoke_formula(
        build_formula_messages(user_message, feedback=feedback, parent=parent,
                               modules=modules))


def formula_agent(state: AgentState):
    """Generate a structured frozen-dessert formula as a JSON object.

    Uses Groq JSON mode and a library-constrained ingredient list so the output
    reliably parses and resolves. main.py runs the domain validation gate on
    this output (and may trigger exactly one repair via regenerate_formula).
    """
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    user_message = user_messages[-1].content
    raw = _invoke_formula(
        build_formula_messages(user_message, modules=state.get("modules")))
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
