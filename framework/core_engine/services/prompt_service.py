from core_engine.schemas.conversation_schemas import (
    DialogueTurn,
)

from core_engine.schemas.prompt_schemas import PromptProfile, PromptSection


def format_dialogue_history_for_prompt(
    dialogue_history: list[DialogueTurn],
    user_label: str = "User",
    assistant_label: str = "Assistant",
) -> str:
    if not dialogue_history:
        return "No previous dialogue."

    formatted_turns: list[str] = []

    for turn in dialogue_history:
        turn_lines = [
            f"Previous subjects: {turn.previous_subject!r}",
            f"Subjects: {turn.subject!r}",
            f"References: {turn.reference!r}",
        ]

        if turn.user is not None:
            route_labels = {
                "potential_noise": "potential noise",
                "backchannel": "backchannel",
                "interruption": "interruption",
            }
            route_label = route_labels.get(turn.route_type)

            if route_label:
                turn_lines.append(
                    f"{user_label} [{route_label}]: "
                    f"{turn.user}"
                )
            else:
                turn_lines.append(
                    f"{user_label}: {turn.user}"
                )

        if turn.assistant is not None:
            turn_lines.append(
                f"{assistant_label}: {turn.assistant}"
            )

        formatted_turns.append(
            "\n".join(turn_lines)
        )

    return "\n\n".join(formatted_turns)


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


def build_prompt(
    user_input: str,
    dialogue_history: list[DialogueTurn],
    profile: PromptProfile,
    context_sections: list[PromptSection] | None = None,
    content_generation_rules: list[str] | None = None,
    additional_policy_sections: list[PromptSection] | None = None,
) -> str:
    context_sections = context_sections or []
    additional_policy_sections = additional_policy_sections or []

    formatted_history = format_dialogue_history_for_prompt(
        dialogue_history=dialogue_history,
        user_label=profile.user_name,
        assistant_label=profile.assistant_name,
    )

    formatted_context = format_prompt_sections(context_sections)

    behavioural_policy = "\n".join(
        f"- {rule}" for rule in profile.behavioural_rules
    )
    selected_content_rules = (
        content_generation_rules
        if content_generation_rules is not None
        else profile.default_content_generation_rules
    )
    content_generation_policy = "\n".join(
        f"- {rule}" for rule in selected_content_rules
    )
    additional_policies = (
        f"\n\n{format_prompt_sections(additional_policy_sections)}"
        if additional_policy_sections
        else ""
    )

    return f"""
{profile.assistant_role}

Behavioural policy:
{behavioural_policy or "- Respond appropriately to the user."}

Content-generation policy:
{content_generation_policy or "- Answer the user's current request directly."}{additional_policies}

Context:
{formatted_context}

Recent dialogue:
{formatted_history}
""".strip()
