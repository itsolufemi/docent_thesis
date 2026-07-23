from conversation_core.memory.conversation_store import (
    close_active_branch,
    create_conversation_branch,
    get_active_branch,
    update_branch_subjects,
)

from conversation_core.schemas.conversation_schemas import (
    ConversationSubject,
)

from conversation_core.schemas.conversation_tool_schemas import (
    CloseActiveBranchArguments,
    CreateConversationBranchArguments,
    ToolSubjectInput,
    UpdateActiveBranchArguments,
)

from conversation_core.schemas.tool_schemas import (
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionResult,
)

from conversation_core.tools.tool_registry import ToolRegistry

def convert_subject_inputs(
    subject_inputs: list[ToolSubjectInput] | None,
) -> list[ConversationSubject] | None:
    if subject_inputs is None:
        return None

    return [
        ConversationSubject(
            label=subject.label,
            reference=subject.reference,
        )
        for subject in subject_inputs
    ]

def handle_create_conversation_branch(
    context: ToolExecutionContext,
    raw_arguments: dict,
) -> ToolExecutionResult:
    arguments = CreateConversationBranchArguments.model_validate(
        raw_arguments
    )

    state = create_conversation_branch(
        conversation_id=context.conversation_id,
        name=arguments.name,
        branch_type=arguments.branch_type,
        current_subjects=(
            convert_subject_inputs(arguments.current_subjects)
            or []
        ),
        remaining_subjects=(
            convert_subject_inputs(arguments.remaining_subjects)
            or []
        ),
    )

    if state is None:
        return ToolExecutionResult(
            tool_name="create_conversation_branch",
            success=False,
            message="The conversation could not be found.",
        )

    active_branch = get_active_branch(
        context.conversation_id
    )

    if active_branch is None:
        return ToolExecutionResult(
            tool_name="create_conversation_branch",
            success=False,
            message="The branch was created but could not be retrieved.",
        )

    return ToolExecutionResult(
        tool_name="create_conversation_branch",
        success=True,
        message=(
            f"Created and activated the "
            f"'{active_branch.name}' branch."
        ),
        data={
            "active_branch": active_branch.model_dump(),
        },
    )

def handle_update_active_branch(
    context: ToolExecutionContext,
    raw_arguments: dict,
) -> ToolExecutionResult:
    arguments = UpdateActiveBranchArguments.model_validate(
        raw_arguments
    )

    active_branch = get_active_branch(
        context.conversation_id
    )

    if active_branch is None:
        return ToolExecutionResult(
            tool_name="update_active_branch",
            success=False,
            message="No active conversation branch was found.",
        )

    state = update_branch_subjects(
        conversation_id=context.conversation_id,
        branch_id=active_branch.branch_id,
        previous_subjects=convert_subject_inputs(
            arguments.previous_subjects
        ),
        current_subjects=convert_subject_inputs(
            arguments.current_subjects
        ),
        remaining_subjects=convert_subject_inputs(
            arguments.remaining_subjects
        ),
    )

    if state is None:
        return ToolExecutionResult(
            tool_name="update_active_branch",
            success=False,
            message="The active branch could not be updated.",
        )

    updated_branch = get_active_branch(
        context.conversation_id
    )

    if updated_branch is None:
        return ToolExecutionResult(
            tool_name="update_active_branch",
            success=False,
            message="The updated branch could not be retrieved.",
        )

    return ToolExecutionResult(
        tool_name="update_active_branch",
        success=True,
        message=(
            f"Updated the '{updated_branch.name}' branch."
        ),
        data={
            "active_branch": updated_branch.model_dump(),
        },
    )

def handle_close_active_branch(
    context: ToolExecutionContext,
    raw_arguments: dict,
) -> ToolExecutionResult:
    arguments = CloseActiveBranchArguments.model_validate(
        raw_arguments
    )

    active_branch = get_active_branch(
        context.conversation_id
    )

    if active_branch is None:
        return ToolExecutionResult(
            tool_name="close_active_branch",
            success=False,
            message="No active conversation branch was found.",
        )

    branch_name = active_branch.name

    try:
        state = close_active_branch(
            context.conversation_id
        )
    except ValueError as error:
        return ToolExecutionResult(
            tool_name="close_active_branch",
            success=False,
            message=str(error),
        )

    if state is None:
        return ToolExecutionResult(
            tool_name="close_active_branch",
            success=False,
            message="The active branch could not be closed.",
        )

    new_active_branch = get_active_branch(
        context.conversation_id
    )

    return ToolExecutionResult(
        tool_name="close_active_branch",
        success=True,
        message=(
            f"Closed the '{branch_name}' bounded branch and "
            "activated a new open branch."
        ),
        data={
            "reason": arguments.reason,
            "closed_branch_id": active_branch.branch_id,
            "active_branch": (
                new_active_branch.model_dump()
                if new_active_branch is not None
                else None
            ),
        },
    )

CREATE_CONVERSATION_BRANCH_DEFINITION = ToolDefinition(
    name="create_conversation_branch",
    description=(
        "Create and activate a new conversation branch when the "
        "conversation begins a distinct activity, such as a tour. "
        "Creating a branch closes the previously active branch."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "A short descriptive name for the branch."
                ),
            },
            "branch_type": {
                "type": "string",
                "enum": ["open", "bounded"],
                "description": (
                    "Use bounded when the activity begins with a "
                    "predefined set of subjects. Otherwise use open."
                ),
            },
            "current_subjects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {
                            "type": "string",
                        },
                        "reference": {
                            "type": ["string", "null"],
                        },
                    },
                    "required": ["label"],
                },
            },
            "remaining_subjects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {
                            "type": "string",
                        },
                        "reference": {
                            "type": ["string", "null"],
                        },
                    },
                    "required": ["label"],
                },
            },
        },
        "required": [
            "name",
            "branch_type",
        ],
    },
)

UPDATE_ACTIVE_BRANCH_DEFINITION = ToolDefinition(
    name="update_active_branch",
    description=(
        "Update the structured subjects of the currently active "
        "conversation branch. Only include subject groups that "
        "should be replaced."
    ),
    parameters={
        "type": "object",
        "properties": {
            "previous_subjects": {
                "type": ["array", "null"],
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "reference": {
                            "type": ["string", "null"],
                        },
                    },
                    "required": ["label"],
                },
            },
            "current_subjects": {
                "type": ["array", "null"],
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "reference": {
                            "type": ["string", "null"],
                        },
                    },
                    "required": ["label"],
                },
            },
            "remaining_subjects": {
                "type": ["array", "null"],
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "reference": {
                            "type": ["string", "null"],
                        },
                    },
                    "required": ["label"],
                },
            },
        },
    },
)

CLOSE_ACTIVE_BRANCH_DEFINITION = ToolDefinition(
    name="close_active_branch",
    description=(
        "Close the active bounded conversation branch when its "
        "activity has been completed or the user has clearly asked "
        "to stop it. A new open branch is activated automatically."
    ),
    parameters={
        "type": "object",
        "properties": {
            "reason": {
                "type": ["string", "null"],
                "description": (
                    "A brief explanation of why the branch is closing."
                ),
            },
        },
    },
)

def register_conversation_tree_tools(
    registry: ToolRegistry,
) -> None:
    registry.register(
        definition=CREATE_CONVERSATION_BRANCH_DEFINITION,
        handler=handle_create_conversation_branch,
    )

    registry.register(
        definition=UPDATE_ACTIVE_BRANCH_DEFINITION,
        handler=handle_update_active_branch,
    )

    registry.register(
        definition=CLOSE_ACTIVE_BRANCH_DEFINITION,
        handler=handle_close_active_branch,
    )
