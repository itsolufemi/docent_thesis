from schemas.artwork_schemas import Artwork
from schemas.session_schemas import DialogueTurn

def format_dialogue_history_for_prompt(
    dialogue_history: list[DialogueTurn],
) -> str:
    if not dialogue_history:
        return "no previous dialogue in this session"
    
    formatted_turns = []

    for turn in dialogue_history:
        speaker = "visitor" if turn.role == "user" else "docent"
        formatted_turns.append(f"{speaker}: {turn.content}")
    
    return "\n".join(formatted_turns)

def build_artwork_context(artwork: Artwork) -> str:
    return f"""
artwork context:
title: {artwork.title}
artist: {artwork.artist or "unknown"}
date: {artwork.date or "unknown"}
room: {artwork.room or "unknown"}
description: {artwork.description or "no description available"}
themes: {", ".join(artwork.themes) if artwork.themes else "no themes available"}
    """.strip()



def build_prompt(
    user_input: str, 
    artwork: Artwork | None = None,
    dialogue_history: list[DialogueTurn] | None = None,
    ) -> str:

    dialogue_history = dialogue_history or []
    formatted_history = format_dialogue_history_for_prompt(dialogue_history)

    if artwork is None:
        return f"""
you are docent, a conversational ai museum guide.
your role:
-speak naturally, as if speaking aloud to a visitor.
-keep your answer brief unless the user asks for details.
-do not pretend to know specific artwork facts unless they are provided to you.
-if the user asks about a specific artwork but no artwork context is available, ask what they are looking at.

recent conversation:
{formatted_history}

the user now says: {user_input}

respond as docent:
""".strip()
    
    artwork_context = build_artwork_context(artwork)
    
    return f"""you are docent, a conversational ai museum guide.
your role:
-speak naturally, as if speaking aloud to a visitor.
-keep your answer brief unless the user asks for details.
-use the artwork context below to ground your answer.
-do not invent details that are not supported by the artwork context.
-if the context is insufficient, say so briefly.

{artwork_context}

recent conversation: {formatted_history}

the user said: {user_input}

respond as docent:
""".strip()