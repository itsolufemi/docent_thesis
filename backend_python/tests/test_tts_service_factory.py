import sys
import unittest
from pathlib import Path


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.services.google_tts_service import (
    GoogleTextToSpeechService,
)
from conversation_core.services.pocket_tts_service import (
    PocketTtsService,
)
from conversation_core.services.tts_service_factory import (
    create_tts_service,
)


class TtsServiceFactoryTest(unittest.TestCase):
    def test_google_selects_google_service(self) -> None:
        self.assertIsInstance(
            create_tts_service("google"),
            GoogleTextToSpeechService,
        )

    def test_kyutai_selects_pocket_service(self) -> None:
        self.assertIsInstance(
            create_tts_service("kyutai_pocket"),
            PocketTtsService,
        )

    def test_unknown_backend_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Unsupported TTS backend",
        ):
            create_tts_service("unknown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
