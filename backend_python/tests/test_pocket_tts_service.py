import sys
import unittest
import wave
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.services.pocket_tts_service import (
    PocketTtsService,
    _float_audio_to_pcm16,
)


class FakeTensor:
    def __init__(self, values) -> None:
        self.values = np.asarray(values, dtype=np.float32)

    def detach(self):
        return self

    def cpu(self):
        return self

    def float(self):
        return self

    def flatten(self):
        return self

    def numpy(self):
        return self.values


class FakeModel:
    sample_rate = 24_000

    def __init__(self) -> None:
        self.voice_calls = 0
        self.generation_calls = 0

    def get_state_for_audio_prompt(self, voice_name):
        self.voice_calls += 1
        return {"voice": voice_name}

    def generate_audio_stream(
        self,
        voice_state,
        text,
        *,
        copy_state,
    ):
        self.generation_calls += 1
        return iter([FakeTensor([-1.0, 0.0, 1.0])])


def create_service() -> PocketTtsService:
    return PocketTtsService(
        language="english",
        default_voice_name="alba",
        default_language_code="en-GB",
    )


class PocketTtsServiceTest(unittest.TestCase):
    def test_model_is_loaded_only_once(self) -> None:
        model = FakeModel()

        class FakeTtsModel:
            load_model = Mock(return_value=model)

        service = create_service()

        with patch.dict(
            sys.modules,
            {
                "pocket_tts": SimpleNamespace(
                    TTSModel=FakeTtsModel
                )
            },
        ):
            self.assertIs(service._ensure_model(), model)
            self.assertIs(service._ensure_model(), model)

        FakeTtsModel.load_model.assert_called_once_with(
            language="english",
            quantize=False,
        )

    def test_voice_state_is_loaded_only_once(self) -> None:
        service = create_service()
        model = FakeModel()
        service._model = model

        first = service._get_voice_state("alba")
        second = service._get_voice_state("alba")

        self.assertIs(first, second)
        self.assertEqual(model.voice_calls, 1)

    def test_float_audio_converts_to_pcm16(self) -> None:
        pcm = _float_audio_to_pcm16(
            FakeTensor([-1.0, 0.0, 1.0])
        )
        samples = np.frombuffer(pcm, dtype="<i2")
        self.assertEqual(
            samples.tolist(),
            [-32767, 0, 32767],
        )

    def test_two_requests_reuse_model_and_voice(self) -> None:
        service = create_service()
        model = FakeModel()
        service._model = model

        list(service.stream_synthesise("First."))
        list(service.stream_synthesise("Second."))

        self.assertEqual(model.voice_calls, 1)
        self.assertEqual(model.generation_calls, 2)

    def test_complete_synthesis_returns_wav(self) -> None:
        service = create_service()
        service._model = FakeModel()

        result = service.synthesise("Hello.")

        self.assertEqual(result.provider_name, "kyutai_pocket")
        self.assertTrue(result.audio.startswith(b"RIFF"))

        with wave.open(BytesIO(result.audio), "rb") as wav:
            self.assertEqual(wav.getframerate(), 24_000)
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getsampwidth(), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
