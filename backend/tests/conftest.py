import os
import sys

# Add backend/ to sys.path so graph, main, llm are importable from tests/.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ChatGroq reads GROQ_API_KEY at instantiation time, before any test fixture
# can patch it. Set a placeholder here so graph.py can import cleanly in CI
# without a real key. Actual LLM calls are mocked per-test in test_formula_forge.py.
os.environ.setdefault("GROQ_API_KEY", "test-key-placeholder")
os.environ.setdefault("LLM_PROVIDER", "groq")
# Matches the repository default. Pinning a retired id here made the suite
# assert against a model nothing can serve, which is harmless while the
# client is mocked and misleading the moment it is not.
os.environ.setdefault("GROQ_MODEL", "openai/gpt-oss-120b")

# Abuse controls: keep default limits out of the suite's way. Individual tests
# override these (main.CHAT_RATE_LIMIT / main.budget) to exercise the controls.
os.environ.setdefault("CHAT_RATE_LIMIT", "100000/minute")
os.environ.setdefault("GLOBAL_DAILY_TOKENS", "100000000")
os.environ.setdefault("SESSION_DAILY_TOKENS", "10000000")

# The startup model check makes a network call to list Groq models. It runs on
# every app fixture, so leaving it on made the suite depend on Groq being
# reachable and tripled its runtime. verify_model_available is tested directly.
os.environ.setdefault("VERIFY_MODEL_ON_STARTUP", "false")
