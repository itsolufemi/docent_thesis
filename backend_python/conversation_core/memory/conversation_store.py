from uuid import uuid4

from ..schemas.conversation_schemas import (
    ConversationBranch,
    ConversationBranchType,
    ConversationState,
    ConversationTree,
    ConversationSubject,
    DialogueRole,
    DialogueTurn,
)

conversations: dict[str, ConversationState] = {}

INTRODUCTION_TEXT_METADATA_KEY = "introduction_text"


def generate_branch_name(tree: ConversationTree) -> str:
    return f"branch-{len(tree.branches) + 1}"


def _add_active_branch(
    tree: ConversationTree,
    *,
    branch_type: ConversationBranchType,
    name: str | None = None,
    current_subjects: list[ConversationSubject] | None = None,
    remaining_subjects: list[ConversationSubject] | None = None,
) -> ConversationBranch:
    branch = ConversationBranch(
        name=name or generate_branch_name(tree),
        branch_type=branch_type,
        status="active",
        current_subjects=current_subjects or [],
        remaining_subjects=remaining_subjects or [],
    )

    tree.branches[branch.branch_id] = branch
    tree.active_branch_id = branch.branch_id

    return branch

def create_conversation() -> ConversationState:
    conversation_id = str(uuid4())

    initial_branch = ConversationBranch(
        name="branch-1",
        branch_type="open",
        status="active",
    )

    conversation_tree = ConversationTree(
        active_branch_id=initial_branch.branch_id,
        branches={
            initial_branch.branch_id: initial_branch,
        },
    )

    state = ConversationState(
        conversation_id=conversation_id,
        conversation_tree=conversation_tree,
    )

    conversations[conversation_id] = state

    return state

def get_conversation(conversation_id:str) -> ConversationState | None:
    return conversations.get(conversation_id)

def get_active_branch(
    conversation_id: str,
) -> ConversationBranch | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None

    tree = state.conversation_tree

    return tree.branches.get(tree.active_branch_id)

def create_conversation_branch(
    conversation_id: str,
    branch_type: ConversationBranchType,
    name: str | None = None,
    current_subjects: list[ConversationSubject] | None = None,
    remaining_subjects: list[ConversationSubject] | None = None,
) -> ConversationState | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None

    tree = state.conversation_tree
    active_branch = tree.branches.get(tree.active_branch_id)

    if active_branch is not None:
        active_branch.status = "closed"

    _add_active_branch(
        tree,
        name=name,
        branch_type=branch_type,
        current_subjects=current_subjects or [],
        remaining_subjects=remaining_subjects or [],
    )

    conversations[conversation_id] = state

    return state

def close_active_branch(
    conversation_id: str,
) -> ConversationState | None:
    return close_bounded_branch(conversation_id)


def close_bounded_branch(
    conversation_id: str,
) -> ConversationState | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None

    tree = state.conversation_tree
    active_branch = tree.branches.get(tree.active_branch_id)

    if active_branch is None:
        return None

    if active_branch.branch_type != "bounded":
        raise ValueError("The active branch is not bounded.")

    active_branch.status = "closed"

    _add_active_branch(
        tree,
        branch_type="open",
    )

    conversations[conversation_id] = state

    return state

def add_subject_to_branch(
    conversation_id: str,
    branch_id: str,
    subject: ConversationSubject,
    subject_group: str,
) -> ConversationState | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None

    branch = state.conversation_tree.branches.get(branch_id)

    if branch is None:
        return None

    subject_lists = {
        "previous": branch.previous_subjects,
        "current": branch.current_subjects,
        "remaining": branch.remaining_subjects,
    }

    target_list = subject_lists.get(subject_group)

    if target_list is None:
        return None

    if subject not in target_list:
        target_list.append(subject)

    conversations[conversation_id] = state

    return state

def get_branch(
    conversation_id: str,
    branch_id: str,
) -> ConversationBranch | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None

    return state.conversation_tree.branches.get(branch_id)

def add_dialogue_turn(
    conversation_id: str,
    role: DialogueRole,
    content: str,
    previous_subject: str | None = None,
    current_subject: str | None = None,
    current_subject_reference: str | None = None,
) -> ConversationState | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None

    turn = DialogueTurn(
        role=role,
        content=content,
        previous_subject=previous_subject,
        current_subject=current_subject,
        current_subject_reference=(
            current_subject_reference
        ),
    )

    state.dialogue_history.append(turn)

    conversations[conversation_id] = state

    return state

def get_recent_conversation_history(
    conversation_id: str,
    limit: int = 6,
) -> list[DialogueTurn]:
    state = get_conversation(conversation_id)

    if state is None:
        return []
    
    return state.dialogue_history[-limit:]


def get_conversation_introduction(
    conversation_id: str,
) -> str | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None

    introduction = state.metadata.get(
        INTRODUCTION_TEXT_METADATA_KEY
    )

    return (
        introduction
        if isinstance(introduction, str)
        else None
    )


def set_conversation_introduction(
    conversation_id: str,
    text: str,
) -> ConversationState | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None

    state.metadata[
        INTRODUCTION_TEXT_METADATA_KEY
    ] = text
    conversations[conversation_id] = state

    return state


