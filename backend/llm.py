import os
from dotenv import load_dotenv
load_dotenv()

def get_llm():
    """Instantiate and return the configured LLM client.

    Provider and model are read from environment variables so the entire graph
    can be pointed at a different backend (OpenAI, Anthropic) with zero code
    changes — only .env needs updating. temperature=0.3 is intentionally low:
    formulation outputs need to be reproducible and grounded, not creative.
    Raises ValueError fast at startup if LLM_PROVIDER is misconfigured, rather
    than failing silently on the first user request.
    """
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model, temperature=0.3)

    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}. Set LLM_PROVIDER=groq in .env.")