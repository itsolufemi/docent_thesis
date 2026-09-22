import os
import sys
import unittest
from pathlib import Path
from statistics import mean

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from conversation_core.api.routes_trp import router as trp_router
from conversation_core.schemas.trp_schemas import TRPPrediction


RUN_TRP_INTEGRATION_TESTS = (
    os.getenv("RUN_TRP_INTEGRATION_TESTS", "").lower()
    in {"1", "true", "yes"}
)
TRP_TEST_REPEATS = int(
    os.getenv("TRP_TEST_REPEATS", "3")
)

TRP_FRAGMENT_CASES = [
    ("tell", False),
    ("tell me", False),
    ("tell me about", False),
    ("tell me about The Arab Tent", True),
    ("I think that", False),
    ("I think that the painting is", False),
    ("I think that the painting is beautiful", True),
]


@unittest.skipUnless(
    RUN_TRP_INTEGRATION_TESTS,
    "Set RUN_TRP_INTEGRATION_TESTS=1 to call the configured TRP model.",
)
class TRPIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(trp_router)
        cls.client = TestClient(app)

    def test_fragment_accuracy_latency_json_and_consistency(self) -> None:
        correct_cases = 0
        all_prediction_seconds: list[float] = []
        report_rows: list[str] = []

        for partial_utterance, expected_complete in TRP_FRAGMENT_CASES:
            predictions: list[TRPPrediction] = []

            for _ in range(TRP_TEST_REPEATS):
                response = self.client.post(
                    "/api/conversation/trp",
                    json={
                        "partial_utterance": partial_utterance,
                        "previous_turns": [],
                    },
                )

                self.assertEqual(
                    response.status_code,
                    200,
                    msg=response.text,
                )

                prediction = TRPPrediction.model_validate(
                    response.json()
                )
                predictions.append(prediction)
                all_prediction_seconds.append(
                    prediction.prediction_seconds
                )

            completion_results = {
                prediction.turn_complete
                for prediction in predictions
            }
            self.assertEqual(
                len(completion_results),
                1,
                msg=(
                    "Inconsistent completion predictions for "
                    f"{partial_utterance!r}: {completion_results}"
                ),
            )

            predicted_complete = predictions[0].turn_complete
            if predicted_complete == expected_complete:
                correct_cases += 1

            report_rows.append(
                f"{partial_utterance!r}: "
                f"expected={expected_complete}, "
                f"predicted={predicted_complete}, "
                "probabilities="
                f"{[item.trp_probability for item in predictions]}, "
                "seconds="
                f"{[item.prediction_seconds for item in predictions]}"
            )

        accuracy = correct_cases / len(TRP_FRAGMENT_CASES)

        print("\nTRP fragment evaluation")
        for report_row in report_rows:
            print(report_row)
        print(f"Accuracy: {accuracy:.2%}")
        print(
            "Average prediction seconds: "
            f"{mean(all_prediction_seconds):.4f}"
        )
        print(
            "Maximum prediction seconds: "
            f"{max(all_prediction_seconds):.4f}"
        )

        self.assertGreaterEqual(
            accuracy,
            0.85,
            msg="TRP fragment accuracy fell below 85%.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
