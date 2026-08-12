from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import numpy as np
import onnxruntime as ort
from transformers import WhisperFeatureExtractor


SMART_TURN_SAMPLE_RATE = 16_000


@dataclass(frozen=True)
class SmartTurnPrediction:
    completion_probability: float
    turn_complete: bool
    feature_extraction_seconds: float
    inference_seconds: float
    total_seconds: float


class SmartTurnService:
    def __init__(
        self,
        model_path: str | Path,
        threshold: float = 0.50,
        *,
        max_audio_seconds: float = 8.0,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                "Smart Turn threshold must be between 0 and 1."
            )

        if max_audio_seconds <= 0:
            raise ValueError(
                "Smart Turn maximum audio duration must be positive."
            )

        resolved_model_path = Path(model_path).resolve()

        if not resolved_model_path.is_file():
            raise FileNotFoundError(
                "Smart Turn ONNX model was not found: "
                f"{resolved_model_path}"
            )

        self.model_path = resolved_model_path
        self.threshold = threshold
        self.max_audio_seconds = max_audio_seconds
        self.maximum_samples = round(
            SMART_TURN_SAMPLE_RATE * max_audio_seconds
        )

        session_options = ort.SessionOptions()
        session_options.execution_mode = (
            ort.ExecutionMode.ORT_SEQUENTIAL
        )
        session_options.inter_op_num_threads = 1
        session_options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        )

        self._session = ort.InferenceSession(
            str(resolved_model_path),
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )
        self._feature_extractor = WhisperFeatureExtractor(
            chunk_length=max_audio_seconds,
        )

    def warm_up(self) -> float:
        started_at = perf_counter()
        silence_samples = np.zeros(
            round(SMART_TURN_SAMPLE_RATE * 0.25),
            dtype="<i2",
        )
        self.predict(
            silence_samples.tobytes(),
            sample_rate=SMART_TURN_SAMPLE_RATE,
            channels=1,
        )
        return perf_counter() - started_at

    @staticmethod
    def _decode_pcm16(
        pcm_audio: bytes,
        *,
        channels: int,
    ) -> np.ndarray:
        if not pcm_audio:
            raise ValueError(
                "Smart Turn audio cannot be empty."
            )

        if channels <= 0:
            raise ValueError(
                "Smart Turn channel count must be positive."
            )

        frame_width = channels * 2

        if len(pcm_audio) % frame_width:
            raise ValueError(
                "PCM16 audio must contain complete sample frames."
            )

        samples = np.frombuffer(
            pcm_audio,
            dtype="<i2",
        ).astype(np.float32)

        if channels > 1:
            samples = samples.reshape(-1, channels).mean(
                axis=1
            )

        return samples / 32768.0

    @staticmethod
    def _resample(
        audio: np.ndarray,
        *,
        source_rate: int,
    ) -> np.ndarray:
        if source_rate <= 0:
            raise ValueError(
                "Smart Turn sample rate must be positive."
            )

        if source_rate == SMART_TURN_SAMPLE_RATE:
            return audio

        target_length = max(
            1,
            round(
                audio.size
                * SMART_TURN_SAMPLE_RATE
                / source_rate
            ),
        )
        source_positions = np.arange(
            audio.size,
            dtype=np.float64,
        )
        target_positions = np.linspace(
            0,
            audio.size,
            num=target_length,
            endpoint=False,
            dtype=np.float64,
        )

        return np.interp(
            target_positions,
            source_positions,
            audio,
        ).astype(np.float32)

    def _prepare_audio(
        self,
        pcm_audio: bytes,
        *,
        sample_rate: int,
        channels: int,
    ) -> np.ndarray:
        audio = self._decode_pcm16(
            pcm_audio,
            channels=channels,
        )
        audio = self._resample(
            audio,
            source_rate=sample_rate,
        )

        if audio.size > self.maximum_samples:
            audio = audio[-self.maximum_samples:]
        elif audio.size < self.maximum_samples:
            audio = np.pad(
                audio,
                (
                    self.maximum_samples - audio.size,
                    0,
                ),
                mode="constant",
            )

        return audio

    def predict(
        self,
        pcm_audio: bytes,
        sample_rate: int = SMART_TURN_SAMPLE_RATE,
        *,
        channels: int = 1,
    ) -> SmartTurnPrediction:
        total_started_at = perf_counter()
        audio = self._prepare_audio(
            pcm_audio,
            sample_rate=sample_rate,
            channels=channels,
        )

        feature_started_at = perf_counter()
        inputs = self._feature_extractor(
            audio,
            sampling_rate=SMART_TURN_SAMPLE_RATE,
            return_tensors="np",
            padding="max_length",
            max_length=self.maximum_samples,
            truncation=True,
            do_normalize=True,
        )
        input_features = (
            inputs.input_features
            .squeeze(0)
            .astype(np.float32)
        )
        input_features = np.expand_dims(
            input_features,
            axis=0,
        )
        feature_extraction_seconds = (
            perf_counter() - feature_started_at
        )

        inference_started_at = perf_counter()
        outputs = self._session.run(
            None,
            {"input_features": input_features},
        )
        inference_seconds = (
            perf_counter() - inference_started_at
        )

        completion_probability = float(
            np.asarray(outputs[0]).squeeze()
        )
        completion_probability = min(
            1.0,
            max(0.0, completion_probability),
        )

        return SmartTurnPrediction(
            completion_probability=(
                completion_probability
            ),
            turn_complete=(
                completion_probability >= self.threshold
            ),
            feature_extraction_seconds=(
                feature_extraction_seconds
            ),
            inference_seconds=inference_seconds,
            total_seconds=(
                perf_counter() - total_started_at
            ),
        )

