from backend_python.conversation_core.schemas.conversation_schemas import DialogueTurn

from backend_python.conversation_core.schemas.prompt_schemas import PromptProfile, PromptSection

def format_dialogue_history_for_prompt(
    dialogue_history: list[DialogueTurn],
    user_label: str = "User",
    assistant_label: str = "Assistant",
) -> str:
    if not dialogue_history:
        return "No previous dialogue."

    formatted_turns = []

    for turn in dialogue_history:
        if turn.role == "user":
            speaker = user_label
        elif turn.role == "assistant":
            speaker = assistant_label
        else:
            speaker = "System"

        formatted_turns.append(f"{speaker}: {turn.content}")

    return "\n".join(formatted_turns)

def format_prompt_sections(
    sections: list[PromptSection],
) -> str:
    visible_sections = [
        section for section in sections if section.content.strip()
    ]

    if not visible_sections:
        return "No additional context."

    blocks = []

    for section in visible_sections:
        blocks.append(
            f"{section.title}:\n{section.content.strip()}"
        )

    return "\n\n".join(blocks)

def build_conversation_prompt(
    user_input: str,
    dialogue_history: list[DialogueTurn],
    profile: PromptProfile,
    context_sections: list[PromptSection] | None = None,
) -> str:
    context_sections = context_sections or []

    formatted_history = format_dialogue_history_for_prompt(
        dialogue_history=dialogue_history,
        user_label=profile.user_name,
        assistant_label=profile.assistant_name,
    )

    formatted_context = format_prompt_sections(context_sections)

    rules = "\n".join(
        f"- {rule}" for rule in profile.behavioural_rules
    )

    return f"""
{profile.assistant_role}

Behavioural rules:
{rules or "- Respond appropriately to the user."}

Context:
{formatted_context}

Recent dialogue:
{formatted_history}

{profile.user_name} says:
{user_input}

Respond as {profile.assistant_name}:
""".strip()