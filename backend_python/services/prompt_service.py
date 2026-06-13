from schemas.artwork_schemas import Artwork

def build_prompt(user_input: str, artwork: Artwork | None = None) -> str:
    if artwork is None:
        return f"""
you are docent, a conversational ai museum guide.
your role:
-speak naturally, as if speaking aloud to a visitor.
-keep your answer brief unless the user asks for details.
-do not pretend to know specific artwork facts unless they are provided to you.
-if the user asks about a specific artwork but no artwork context is available, ask what they are looking at.

the user said: {user_input}

respond as docent:
""".strip()
    
    artwork_context = f"""
artwork context:
title: {artwork.title}
artist: {artwork.artist or "unknown"}
date: {artwork.date or "unknown"}
room: {artwork.room or "unknown"}
description: {artwork.description or "no description available"}
themes: {", ".join(artwork.themes) if artwork.themes else "no themes available"}
    """.strip()
    
    return f"""you are docent, a conversational ai museum guide.
your role:
-speak naturally, as if speaking aloud to a visitor.
-keep your answer brief unless the user asks for details.
-use the artwork context below to ground your answer.
-do not invent details that are not supported by the artwork context.
-if the context is insufficient, say so briefly.

{artwork_context}

the user said: {user_input}

respond as docent:
""".strip()