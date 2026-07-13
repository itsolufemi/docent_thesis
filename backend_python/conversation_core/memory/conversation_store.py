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

def create_conversation() -> ConversationState:
    conversation_id = str(uuid4())

    root_branch = ConversationBranch(
        name="main",
        branch_type="open",
        parent_branch_id=None,
        status="active",
    )

    conversation_tree = ConversationTree(
        root_branch_id=root_branch.branch_id,
        active_branch_id=root_branch.branch_id,
        branches={
            root_branch.branch_id: root_branch,
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
    name: str,
    branch_type: ConversationBranchType,
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

    branch = ConversationBranch(
        parent_branch_id=tree.root_branch_id,
        name=name,
        branch_type=branch_type,
        status="active",
        current_subjects=current_subjects or [],
        remaining_subjects=remaining_subjects or [],
    )

    tree.branches[branch.branch_id] = branch
    tree.active_branch_id = branch.branch_id

    conversations[conversation_id] = state

    return state

def update_branch_subjects(
    conversation_id: str,
    branch_id: str,
    previous_subjects: list[ConversationSubject] | None = None,
    current_subjects: list[ConversationSubject] | None = None,
    remaining_subjects: list[ConversationSubject] | None = None,
) -> ConversationState | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None

    branch = state.conversation_tree.branches.get(branch_id)

    if branch is None:
        return None

    if previous_subjects is not None:
        branch.previous_subjects = previous_subjects

    if current_subjects is not None:
        branch.current_subjects = current_subjects

    if remaining_subjects is not None:
        branch.remaining_subjects = remaining_subjects

    conversations[conversation_id] = state

    return state

def set_current_subject(
    conversation_id: str,
    subject_reference: str,
    subject_label: str | None = None,
) -> ConversationState | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None

    tree = state.conversation_tree
    active_branch = tree.branches.get(tree.active_branch_id)

    if active_branch is None:
        return None

    for current_subject in active_branch.current_subjects:
        if current_subject not in active_branch.previous_subjects:
            active_branch.previous_subjects.append(current_subject)

    active_branch.current_subjects = [
        ConversationSubject(
            label=subject_label or subject_reference,
            reference=subject_reference,
        )
    ]

    conversations[conversation_id] = state

    return state

def close_active_branch(
    conversation_id: str,
) -> ConversationState | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None

    tree = state.conversation_tree
    active_branch = tree.branches.get(tree.active_branch_id)

    if active_branch is None:
        return None

    active_branch.status = "closed"

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
    ) -> ConversationState | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None
    
    turn = DialogueTurn(
        role=role,
        content=content
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


