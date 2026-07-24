import sys
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.services.transcription_service import (
    TranscriptionService,
)


class TranscriptionServiceTest(unittest.TestCase):
    @patch(
        "conversation_core.services.transcription_service."
        "WhisperModel"
    )
    def test_model_is_loaded_once_and_reused(
        self,
        whisper_model,
    ) -> None:
        service = TranscriptionService(
            model_name="base.en",
            device="cpu",
            compute_type="int8",
        )

        first_model = service._get_model()
        second_model = service._get_model()

        self.assertIs(first_model, second_model)
        whisper_model.assert_called_once_with(
            "base.en",
            device="cpu",
            compute_type="int8",
        )

    def test_transcribe_file_combines_segments(self) -> None:
        service = TranscriptionService(
            model_name="base.en",
            device="cpu",
            compute_type="int8",
        )
        fake_model = Mock()
        fake_segments = iter(
            [
                SimpleNamespace(
                    start=0.0,
                    end=1.2,
                    text=" Tell me about",
                ),
                SimpleNamespace(
                    start=1.2,
                    end=2.5,
                    text=" The Arab Tent.",
                ),
            ]
        )
        fake_info = SimpleNamespace(
            language="en",
            language_probability=0.99,
            duration=2.5,
        )
        fake_model.transcribe.return_value = (
            fake_segments,
            fake_info,
        )
        service._model = fake_model

        with NamedTemporaryFile(suffix=".wav") as audio_file:
            result = service.transcribe_file(audio_file.name)

        self.assertEqual(
            result.text,
            "Tell me about The Arab Tent.",
        )
        self.assertEqual(result.language, "en")
        self.assertEqual(result.language_probability, 0.99)
        self.assertEqual(result.duration_seconds, 2.5)
        self.assertEqual(len(result.segments), 2)

        fake_model.transcribe.assert_called_once_with(
            audio_file.name,
            language="en",
            beam_size=1,
            condition_on_previous_text=False,
            vad_filter=False,
        )

    def test_missing_audio_file_is_rejected_before_model_load(self) -> None:
        service = TranscriptionService(
            model_name="base.en",
            device="cpu",
            compute_type="int8",
        )

        with self.assertRaises(FileNotFoundError):
            service.transcribe_file("missing-audio.wav")

        self.assertIsNone(service._model)

    def test_transcribe_pcm16_normalises_audio(self) -> None:
        service = TranscriptionService(
            model_name="base.en",
            device="cpu",
            compute_type="int8",
        )
        fake_model = Mock()
        fake_model.transcribe.return_value = (
            iter(
                [
                    SimpleNamespace(
                        start=0.0,
                        end=1.0,
                        text=" Test audio.",
                    ),
                ]
            ),
            SimpleNamespace(
                language="en",
                language_probability=0.99,
                duration=1.0,
            ),
        )
        service._model = fake_model
        pcm_bytes = np.array(
            [-32768, 0, 32767],
            dtype="<i2",
        ).tobytes()

        result = service.transcribe_pcm16(
            pcm_bytes,
            sample_rate=16_000,
            channels=1,
        )

        self.assertEqual(result.text, "Test audio.")

        audio_argument = (
            fake_model.transcribe.call_args.args[0]
        )
        self.assertEqual(audio_argument.dtype, np.float32)
        self.assertAlmostEqual(float(audio_argument[0]), -1.0)
        self.assertAlmostEqual(float(audio_argument[1]), 0.0)
        self.assertAlmostEqual(
            float(audio_argument[2]),
            32767 / 32768,
        )

    def test_transcribe_pcm16_rejects_invalid_input(self) -> None:
        service = TranscriptionService(
            model_name="base.en",
            device="cpu",
            compute_type="int8",
        )

        with self.assertRaisesRegex(
            ValueError,
            "buffer is empty",
        ):
            service.transcribe_pcm16(
                b"",
                sample_rate=16_000,
            )

        with self.assertRaisesRegex(
            ValueError,
            "16000 Hz",
        ):
            service.transcribe_pcm16(
                b"\x00\x00",
                sample_rate=44_100,
            )

        with self.assertRaisesRegex(
            ValueError,
            "mono audio",
        ):
            service.transcribe_pcm16(
                b"\x00\x00",
                sample_rate=16_000,
                channels=2,
            )

        with self.assertRaisesRegex(
            ValueError,
            "even number of bytes",
        ):
            service.transcribe_pcm16(
                b"\x00",
                sample_rate=16_000,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
