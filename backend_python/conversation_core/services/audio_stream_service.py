from dataclasses import dataclass, field

from conversation_core.schemas.audio_stream_schemas import (
    AudioStreamSummary,
)


@dataclass
class AudioStreamBuffer:
    sample_rate: int
    channels: int
    sample_width_bytes: int

    chunks: list[bytes] = field(default_factory=list)
    total_bytes: int = 0

    def append(self, chunk: bytes) -> None:
        if not chunk:
            return

        self.chunks.append(chunk)
        self.total_bytes += len(chunk)

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def bytes_per_sample_frame(self) -> int:
        return self.sample_width_bytes * self.channels

    @property
    def total_samples(self) -> int:
        if self.bytes_per_sample_frame <= 0:
            return 0

        return self.total_bytes // self.bytes_per_sample_frame

    @property
    def duration_seconds(self) -> float:
        if self.sample_rate <= 0:
            return 0.0

        return self.total_samples / self.sample_rate

    def to_bytes(self) -> bytes:
        return b"".join(self.chunks)

    def summary(self) -> AudioStreamSummary:
        return AudioStreamSummary(
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width_bytes=self.sample_width_bytes,
            chunk_count=self.chunk_count,
            total_bytes=self.total_bytes,
            total_samples=self.total_samples,
            duration_seconds=self.duration_seconds,
        )
