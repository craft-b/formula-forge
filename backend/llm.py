import os
from dotenv import load_dotenv
load_dotenv()

def get_llm():
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.3
        )
    
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")