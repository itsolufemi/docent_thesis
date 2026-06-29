from schemas.artwork_schemas import Artwork
from schemas.session_schemas import DialogueTurn
from schemas.retrieval_schemas import RetrievedArtwork


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

def build_retrieved_artworks_context(
    retrieved_artworks: list[RetrievedArtwork],
) -> str:
    if not retrieved_artworks:
        return ""

    blocks = []

    for index, retrieved in enumerate(retrieved_artworks, start=1):
        artwork = retrieved.artwork

        block = f"""
Retrieved record {index}:
Painting index: {artwork.painting_index}
Title: {artwork.title}
Artist: {artwork.artist or "unknown"}
School: {getattr(artwork, "school", None) or "unknown"}
Date: {artwork.date or "unknown"}
Object type: {getattr(artwork, "object_type", None) or "unknown"}
Medium: {artwork.medium or "unknown"}
Room: {getattr(artwork, "room_name", None) or artwork.room or "unknown"}
Inventory number: {getattr(artwork, "inventory_number", None) or "unknown"}
Matched fields: {", ".join(retrieved.matched_fields)}
Retrieval score: {retrieved.score}
Snippet: {retrieved.snippet or "no snippet available"}
Description: {artwork.description or "no description available"}
Provenance: {getattr(artwork, "provenance", None) or "no provenance available"}
Record URL: {getattr(artwork, "url", None) or "no source URL available"}
""".strip()
        
        blocks.append(block)
    
    return "Retrieved Wallace Collection records:\n\n" + "\n\n".join(blocks)


def build_prompt(
    user_input: str, 
    artwork: Artwork | None = None,
    dialogue_history: list[DialogueTurn] | None = None,
    retrieved_artworks: list[RetrievedArtwork] | None = None,
    ) -> str:

    dialogue_history = dialogue_history or []
    retrieved_artworks = retrieved_artworks or []

    formatted_history = format_dialogue_history_for_prompt(dialogue_history)
    retrieved_artworks_context = build_retrieved_artworks_context(
        retrieved_artworks
    )

    if artwork is None and retrieved_artworks:
        return f"""
you are docent, a conversational ai museum guide.
your role:
-speak naturally, as if speaking aloud to a visitor.
-keep your answer brief unless the user asks for details.
-do not pretend to know specific artwork facts unless they are provided to you.
-if the user asks about a specific artwork but no artwork context is available, ask what they are looking at.

{retrieved_artworks_context}

recent conversation:
{formatted_history}

the user now says: {user_input}

respond as docent:
""".strip()
    
    if artwork is None:
        return f"""
You are Docent, a conversational AI museum guide.

Your role:
- Speak naturally, as if speaking aloud to a visitor.
- Keep your answer brief unless the user asks for detail.
- Use the recent conversation to understand follow-up questions.
- Do not pretend to know specific artwork facts unless they are provided to you.
- If the user asks about a specific artwork but no artwork context is available, ask what artwork they are looking at.

Recent conversation:
{formatted_history}

The visitor now says:
{user_input}

Respond as Docent:
""".strip()
    
    artwork_context = build_artwork_context(artwork)
    
    return f"""
you are docent, a conversational ai museum guide.

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