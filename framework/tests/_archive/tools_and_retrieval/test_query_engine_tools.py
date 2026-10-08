import sys
from pathlib import Path

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from core_engine.memory.conversation_store import (
    create_conversation,
    get_conversation,
)

from core_engine.services.query_service import (
    default_query_engine,
)


state = create_conversation()

result = default_query_engine.generate_response(
    text=(
        "Start a bounded gallery tour. "
        "Begin with The Swing, followed by "
        "The Laughing Cavalier and The Arab Tent."
    ),
    conversation_id=state.conversation_id,
    include_debug=True,
)

print("QUERY RESULT")
print(result.model_dump_json(indent=2))

updated_state = get_conversation(
    state.conversation_id
)

assert updated_state is not None

print("\nUPDATED CONVERSATION")
print(updated_state.model_dump_json(indent=2))