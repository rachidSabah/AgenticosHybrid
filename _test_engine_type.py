import sys

sys.path.insert(0, ".")
try:
    from core.contracts.execution_engine import EngineType

    print("EngineType has OPENCODE:", hasattr(EngineType, "OPENCODE"))
    print("EngineType has AGY_CLI:", hasattr(EngineType, "AGY_CLI"))
    print("EngineType has OLLAMA:", hasattr(EngineType, "OLLAMA"))
    print("EngineType members:", [e.value for e in EngineType])
except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Error: {e}")
