import os
import sys

# Add backend/ to sys.path so graph, main, llm are importable from tests/.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ChatGroq reads GROQ_API_KEY at instantiation time, before any test fixture
# can patch it. Set a placeholder here so graph.py can import cleanly in CI
# without a real key. Actual LLM calls are mocked per-test in test_formula_forge.py.
os.environ.setdefault("GROQ_API_KEY", "test-key-placeholder")
os.environ.setdefault("LLM_PROVIDER", "groq")
os.environ.setdefault("GROQ_MODEL", "llama-3.3-70b-versatile")

# Abuse controls: keep default limits out of the suite's way. Individual tests
# override these (main.CHAT_RATE_LIMIT / main.budget) to exercise the controls.
os.environ.setdefault("CHAT_RATE_LIMIT", "100000/minute")
os.environ.setdefault("GLOBAL_DAILY_TOKENS", "100000000")
os.environ.setdefault("SESSION_DAILY_TOKENS", "10000000")
