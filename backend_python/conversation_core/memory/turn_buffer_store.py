from conversation_core.schemas.turn_buffer_schemas import TurnBufferState


class TurnBufferStore:
    def __init__(self) -> None:
        self._buffers: dict[str, TurnBufferState] = {}

    def get_or_create(
        self,
        conversation_id: str,
    ) -> TurnBufferState:
        existing = self._buffers.get(conversation_id)

        if existing is not None:
            return existing

        buffer = TurnBufferState(
            conversation_id=conversation_id,
        )
        self._buffers[conversation_id] = buffer
        return buffer

    def clear(
        self,
        conversation_id: str,
    ) -> TurnBufferState:
        buffer = TurnBufferState(
            conversation_id=conversation_id,
        )
        self._buffers[conversation_id] = buffer
        return buffer


turn_buffer_store = TurnBufferStore()
