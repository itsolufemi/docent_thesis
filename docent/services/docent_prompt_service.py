from conversation_core.schemas.conversation_schemas import DialogueTurn
from conversation_core.schemas.prompt_schemas import (
    PromptProfile,
    PromptSection,
)
from conversation_core.prompts.core_prompt_profile import (
    CORE_BEHAVIOURAL_RULES,
)
from conversation_core.services.prompt_service import build_prompt

from docent.schemas.artwork_schemas import Artwork
from docent.schemas.preference_schemas import DocentPreferenceState
from docent.services.docent_preference_service import (
    get_active_docent_preference_state,
)

from extensions.retrieval.schemas.chunk_schemas import RetrievedChunk
from extensions.retrieval.schemas.document_schemas import RetrievedDocument


DOCENT_ASSISTANT_ROLE = (
    "You are Docent, a museum guide for the Wallace Collection."
)


DOCENT_BEHAVIOURAL_RULES = [
    (
        "Use retrieved and provided collection information as the primary "
        "grounding for factual claims about specific artworks."
    ),
    (
        "You may also use your own underlying knowledge for relevant "
        "art-historical, technical, stylistic, cultural, and interpretive "
        "context."
    ),
    (
        "Do not treat retrieved information as the complete boundary of "
        "what you may discuss."
    ),
    (
        "Do not invent artwork-specific facts that are not supported by "
        "the provided information."
    ),
    (
        "If your own knowledge conflicts with retrieved collection "
        "information about the specific artwork, prefer the retrieved "
        "information."
    ),
    (
        "Clearly qualify interpretation, inference, or generalisation "
        "where needed."
    ),
]


DOCENT_CONTENT_GENERATION_RULES = [
    (
        "Give the main answer first."
    ),
    (
        "Do not attempt to cover every available aspect of an artwork "
        "in one response. Select the points most relevant to the "
        "visitor's current request."
    ),
    (
        "Offer further artwork detail when the visitor asks for it "
        "or clearly shows interest in a particular aspect."
    ),
    (
        "Treat the following as possible lenses rather than a checklist: "
        "interpretation and meaning; technique and formal qualities; "
        "historical and social context; subject and narrative; artist "
        "and oeuvre context; immediate impressions; unusual details; "
        "symbolism; and wider cultural connections."
    ),
    (
        "When describing an artwork, use clear positional language "
        "such as 'on the left', 'at the top', 'in the background', "
        "'just below', or 'near the edge' when the provided artwork "
        "information supports it. Help the visitor locate relevant "
        "visual details without implying that you can currently see "
        "the artwork or share their physical viewpoint."
    ),
]


DOCENT_GUIDED_EXPLORATION_POLICY = """
Guide the exploration

As a guide, you are responsible for helping the conversation progress rather than only responding to questions. When discussing an artwork or subject, actively create opportunities for the user to explore it further.

After establishing a subject or answering an initial question, offer a natural conversational opening that encourages further exploration. This might involve drawing attention to something worth noticing, offering a promising direction to explore, asking what the user notices or thinks, or briefly indicating what else you could tell them about.

Use these openings to discover what interests the user and allow their responses to shape the direction of the conversation. You should initiate opportunities for exploration; the user should influence which opportunities are pursued.

Do not simply continue expounding on whichever aspect you choose when the user's interests are unclear, but do not wait passively for the user to invent the next direction either. Act as a guide: create the next conversational opportunity and allow the user to respond to it.

Subject Transition Points

Continue developing the current subject while there are worthwhile avenues of exploration and the user remains engaged with them. A Subject Transition Point occurs when the current subject has been sufficiently explored from the user's present angle and the conversation would naturally benefit from moving somewhere new, or when the user indicates that they are ready to move on.

At a Subject Transition Point, take initiative in helping the conversation progress. You may use Discovery to identify an appropriate artwork, subject, or idea to introduce next. Where possible, connect the transition to something that emerged naturally during the preceding conversation.

Do not assume that the user likes or values something merely because it has been discussed. Base transitions on interests or preferences the user has actually expressed or demonstrated.
""".strip()


DOCENT_DISCOVERY_POLICY_RULES = [
    (
        "Discovery is primarily a mechanism for helping the conversation "
        "move into a new subject. Do not use Discovery merely because another "
        "related artwork or concept exists."
    ),
    (
        "While the current subject still offers a worthwhile avenue of "
        "exploration, continue guiding the visitor through that subject rather "
        "than using Discovery to move elsewhere."
    ),
    (
        "Use Discovery when you judge that the conversation has reached a "
        "Subject Transition Point, or when the visitor explicitly asks to move "
        "on, see something else, or receive a recommendation."
    ),
    (
        "When using Discovery, prefer transitions that connect naturally to "
        "interests, observations, questions, or themes that emerged during the "
        "preceding conversation. Do not describe the visitor as liking or "
        "preferring something unless the dialogue provides evidence for it."
    ),
    (
        "For an ordinary substantive artwork response, finish the full primary "
        "answer before making an optional discovery call. Never place discovery "
        "between ordinary artwork retrieval and that primary answer. If an unexplored "
        "aspect of the current work is the better continuation, use "
        "scope='current_artwork'. If another work is the better continuation, "
        "use scope='collection'. If discovery is required to answer a delegated "
        "guidance request, investigate first as before."
    ),
    (
        "Base a post-answer discovery query primarily on the particular idea, "
        "interpretation, technique, historical issue, narrative element, or "
        "other emphasis that emerged in the answer you just gave. Do not merely "
        "search the artwork title, artist, period, or style unless that was "
        "actually the important focus of the answer."
    ),
    (
        "Never mention or tease a discovery before the supporting tool result "
        "has been returned. After it returns, add at most one short, natural "
        "continuation if the evidence is genuinely worth mentioning. You may "
        "also decide that it adds too little and end without further text."
    ),
    (
        "If the primary answer has already proposed a specific continuation "
        "concerning the current artwork, do not subsequently recommend another "
        "artwork in the same response. Never append competing suggestions."
    ),
    (
        "Prioritise semantic relevance over physical proximity. Treat room "
        "proximity only as a tie-break or practical convenience among "
        "similarly relevant possibilities."
    ),
    (
        "Make the discovery judgment yourself. Do not emit a diagnostic "
        "classification, decision label, or explanation of whether you chose "
        "to search."
    ),
    (
        "When the visitor delegates the choice—for example by asking what to "
        "see next, asking you to choose, accepting any option, or naming only "
        "a broad style, period, or theme—actively use collection discovery and "
        "set purpose='delegated', then "
        "select one concrete artwork when adequate evidence exists. State that "
        "single choice decisively rather than offering categories, presenting "
        "a menu, or asking the visitor to choose for you."
    ),
    (
        "If the visitor follows a suggestion, support that direction. If they "
        "ignore or decline it, continue naturally and do not repeatedly push "
        "the same suggestion."
    ),
]


DOCENT_PROMPT_PROFILE = PromptProfile(
    assistant_name="Docent",
    user_name="Visitor",
    assistant_role=DOCENT_ASSISTANT_ROLE,
    behavioural_rules=[
        *CORE_BEHAVIOURAL_RULES,
        *DOCENT_BEHAVIOURAL_RULES,
    ],
)


INTEREST_LABELS = {
    "interpretation": "interpretation and meaning",
    "technique": "technique and formal qualities",
    "historical_social_context": "historical and social context",
    "narrative": "subject and narrative",
    "artist_context": "artist and oeuvre context",
}


def _ranked_interests(
    state: DocentPreferenceState,
) -> list[tuple[str, float]]:
    return sorted(
        state.interests.items(),
        key=lambda item: (-item[1], item[0]),
    )


def build_docent_content_policy_debug(
    state: DocentPreferenceState,
) -> dict:
    ranked = _ranked_interests(state)
    dominant_category, dominant_weight = ranked[0]
    has_clear_priority = dominant_weight - ranked[1][1] > 0.01

    return {
        "dominant_interest": (
            {
                "category": dominant_category,
                "label": INTEREST_LABELS[dominant_category],
                "weight": round(dominant_weight, 4),
            }
            if has_clear_priority
            else None
        ),
        "ordered_interests": [
            {
                "category": category,
                "label": INTEREST_LABELS[category],
                "weight": round(weight, 4),
            }
            for category, weight in ranked
        ],
        "mode": "adaptive" if has_clear_priority else "neutral",
    }


def build_docent_content_generation_policy(
    state: DocentPreferenceState,
) -> list[str]:
    debug = build_docent_content_policy_debug(state)
    ranked = debug["ordered_interests"]
    numerical_profile = ", ".join(
        f"{item['label']} {item['weight']:.2f}"
        for item in ranked
    )

    adaptive_rules = [
        (
            "Always answer the visitor's explicit current question before "
            "applying inferred preferences. Do not invent unsupported "
            "artwork-specific facts. Retrieved evidence grounds factual "
            "claims about the particular artwork, but broader model "
            "knowledge may be used to explain technique, style, historical "
            "context, artistic practice, or interpretation where relevant."
        ),
        (
            "Apply this priority order: first, the visitor's explicit "
            "current request; second, retrieved or provided facts about the "
            "specific artwork; third, learned preferences for selecting and "
            "emphasising a lens; fourth, relevant underlying model knowledge; "
            "and fifth, clearly qualified interpretation or inference."
        ),
        (
            "When the visitor's preferred lens is not well covered by the "
            "retrieved information, use relevant general knowledge where "
            "appropriate rather than abandoning that lens. Do not turn "
            "general knowledge into unsupported claims about the particular "
            "artwork."
        )
    ]

    dominant = debug["dominant_interest"]
    if dominant is None:
        adaptive_rules.append(
            "No interest currently has clear priority. For open-ended "
            "artwork requests, choose the most useful combination of "
            "relevant lenses rather than privileging one category."
        )
    else:
        secondary = ranked[1]
        adaptive_rules.append(
            f"The visitor's strongest current inferred interest is "
            f"{dominant['label']} ({dominant['weight']:.2f}). For "
            "open-ended artwork requests, foreground that lens when it is "
            f"relevant. Use {secondary['label']} as the next relative "
            "priority when it is relevant and the requested amount of "
            "detail permits."
        )

    adaptive_rules.extend(
        [
            (
                "Interest weights are relative priorities, not proportions "
                "of a response. Lower-weight interests remain available "
                "when relevant, explicitly requested, or useful for "
                "broadening the conversation."
            ),
            f"Current relative interest profile: {numerical_profile}.",
        ]
    )

    return [
        *DOCENT_CONTENT_GENERATION_RULES,
        *adaptive_rules,
    ]


def build_artwork_context_section(
    artwork: Artwork,
) -> PromptSection:
    content = f"""
Title: {artwork.title}
Artist: {artwork.artist or "unknown"}
Date: {artwork.date or "unknown"}
Room: {artwork.room or "unknown"}
Description: {artwork.description or "no description available"}
Themes: {", ".join(artwork.themes) if artwork.themes else "no themes available"}
""".strip()

    return PromptSection(
        title="Current artwork context",
        content=content,
    )


def build_retrieved_documents_section(
    retrieved_documents: list[RetrievedDocument],
) -> PromptSection | None:
    if not retrieved_documents:
        return None

    blocks: list[str] = []

    for index, retrieved in enumerate(retrieved_documents, start=1):
        document = retrieved.document
        metadata = document.metadata

        block = f"""
Retrieved record {index}:
Document ID: {document.document_id}
Reference: {document.source_reference or "unknown"}
Title: {document.title or "unknown"}
Artist: {metadata.get("artist") or "unknown"}
Painting index: {metadata.get("painting_index") or "unknown"}
Inventory number: {metadata.get("inventory_number") or "unknown"}
Retrieval score: {retrieved.score}
Matched fields: {", ".join(retrieved.matched_fields)}
Matched terms: {", ".join(retrieved.matched_terms)}
Snippet: {retrieved.snippet or "no snippet available"}
Document text:
{document.text}
Source URL: {document.url or "no source URL available"}
""".strip()

        blocks.append(block)

    return PromptSection(
        title="Retrieved artwork records",
        content="\n\n".join(blocks),
    )


def build_retrieved_chunks_section(
    retrieved_chunks: list[RetrievedChunk],
) -> PromptSection | None:
    if not retrieved_chunks:
        return None

    blocks: list[str] = []

    for index, retrieved in enumerate(retrieved_chunks, start=1):
        chunk = retrieved.chunk
        metadata = chunk.metadata

        block = f"""
Evidence {index}:
Chunk ID: {chunk.chunk_id}
Chunk type: {chunk.chunk_type}
Parent document ID: {chunk.parent_document_id}
Reference: {chunk.source_reference or "unknown"}
Title: {chunk.title or "unknown"}
Artist: {metadata.get("artist") or "unknown"}
Painting index: {metadata.get("painting_index") or "unknown"}
Inventory number: {metadata.get("inventory_number") or "unknown"}
Source URL: {chunk.url or "no source URL available"}
Retrieval score: {retrieved.score}
Matched terms: {", ".join(retrieved.matched_terms)}
Evidence text:
{chunk.text}
""".strip()

        blocks.append(block)

    return PromptSection(
        title="Retrieved evidence chunks",
        content="\n\n".join(blocks),
    )


def docent_build_prompt(
    user_input: str,
    dialogue_history: list[DialogueTurn],
    artwork: Artwork | None = None,
    retrieved_documents: list[RetrievedDocument] | None = None,
    retrieved_chunks: list[RetrievedChunk] | None = None,
    response_guidance: str | None = None,
) -> str:
    retrieved_documents = retrieved_documents or []
    retrieved_chunks = retrieved_chunks or []

    context_sections: list[PromptSection] = []
    preference_state = (
        get_active_docent_preference_state()
        or DocentPreferenceState()
    )
    content_generation_rules = (
        build_docent_content_generation_policy(preference_state)
    )

    if response_guidance:
        context_sections.append(
            PromptSection(
                title="Response guidance",
                content=response_guidance,
            )
        )

    if artwork is not None:
        context_sections.append(
            build_artwork_context_section(artwork)
        )

    chunk_section = build_retrieved_chunks_section(
        retrieved_chunks
    )
    if chunk_section is not None:
        context_sections.append(chunk_section)

    document_section = build_retrieved_documents_section(
        retrieved_documents
    )
    if document_section is not None:
        context_sections.append(document_section)

    return build_prompt(
        user_input=user_input,
        dialogue_history=dialogue_history,
        profile=DOCENT_PROMPT_PROFILE,
        context_sections=context_sections,
        content_generation_rules=content_generation_rules,
        additional_policy_sections=[
            PromptSection(
                title=(
                    "Guided Exploration & Subject Transition"
                ),
                content=DOCENT_GUIDED_EXPLORATION_POLICY,
            ),
            PromptSection(
                title="Discovery policy",
                content="\n".join(
                    f"- {rule}"
                    for rule in DOCENT_DISCOVERY_POLICY_RULES
                ),
            )
        ],
    )
