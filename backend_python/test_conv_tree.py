from conversation_core.memory.conversation_store import (
    close_active_branch,
    create_conversation,
    create_conversation_branch,
    update_branch_subjects,
)

from conversation_core.schemas.conversation_schemas import (
    ConversationSubject,
)


state = create_conversation()
conversation_id = state.conversation_id

tour_state = create_conversation_branch(
    conversation_id=conversation_id,
    name="gallery tour",
    branch_type="bounded",
    current_subjects=[
        ConversationSubject(label="The Swing"),
    ],
    remaining_subjects=[
        ConversationSubject(label="The Laughing Cavalier"),
        ConversationSubject(label="The Arab Tent"),
    ],
)

assert tour_state is not None

tour_branch_id = tour_state.conversation_tree.active_branch_id

updated_state = update_branch_subjects(
    conversation_id=conversation_id,
    branch_id=tour_branch_id,
    previous_subjects=[
        ConversationSubject(label="The Swing"),
    ],
    current_subjects=[
        ConversationSubject(label="The Laughing Cavalier"),
    ],
    remaining_subjects=[
        ConversationSubject(label="The Arab Tent"),
    ],
)

assert updated_state is not None

print("UPDATED STATE")
print(updated_state.model_dump_json(indent=2))

closed_state = close_active_branch(conversation_id)

assert closed_state is not None

print("\nCLOSED STATE")
print(closed_state.model_dump_json(indent=2))