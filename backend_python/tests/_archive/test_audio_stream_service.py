import sys
import unittest
from pathlib import Path


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))


from conversation_core.services.audio_stream_service import (
    AudioStreamBuffer,
)


class AudioStreamBufferTest(unittest.TestCase):
    def test_pcm16_duration_is_calculated(self) -> None:
        audio_buffer = AudioStreamBuffer(
            sample_rate=16_000,
            channels=1,
            sample_width_bytes=2,
        )

        audio_buffer.append(b"\x00\x00" * 16_000)

        self.assertEqual(audio_buffer.total_bytes, 32_000)
        self.assertEqual(audio_buffer.total_samples, 16_000)
        self.assertEqual(audio_buffer.duration_seconds, 1.0)
        self.assertEqual(audio_buffer.chunk_count, 1)

    def test_multiple_chunks_are_combined(self) -> None:
        audio_buffer = AudioStreamBuffer(
            sample_rate=16_000,
            channels=1,
            sample_width_bytes=2,
        )

        audio_buffer.append(b"\x01\x00")
        audio_buffer.append(b"\x02\x00")

        self.assertEqual(audio_buffer.chunk_count, 2)
        self.assertEqual(audio_buffer.total_bytes, 4)
        self.assertEqual(
            audio_buffer.to_bytes(),
            b"\x01\x00\x02\x00",
        )

    def test_empty_chunk_is_ignored(self) -> None:
        audio_buffer = AudioStreamBuffer(
            sample_rate=16_000,
            channels=1,
            sample_width_bytes=2,
        )

        audio_buffer.append(b"")

        self.assertEqual(audio_buffer.chunk_count, 0)
        self.assertEqual(audio_buffer.total_bytes, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
