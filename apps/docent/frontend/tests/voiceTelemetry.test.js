import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildVoiceTelemetryPayload,
  sendCompletedVoiceTelemetry,
} from '../src/audio/voiceTelemetry.js';


test(
  (
    'buildVoiceTelemetryPayload includes '
    + 'LLM, TTS, playback and underrun data'
  ),
  () => {
    const timing = {
      firstDeltaPayload: {
        seconds: 0.8248,
        timings: [
          {
            name:
              'context_resolution_seconds',
            seconds: 0.1697,
          },
        ],
      },

      firstAudioPayload: {
        queryToFirstAudioSeconds:
          1.3972,
        ttsRequestToFirstAudioSeconds:
          0.2787,
      },

      playbackPayload: {
        queryToPlaybackSeconds:
          1.4044,
        firstAudioToPlaybackSeconds:
          0.0072,
      },

      ttsGenerations: [
        {
          generationSeconds:
            4.4248,
          audioDurationSeconds:
            6.08,
          realtimeFactor:
            0.7278,
        },
      ],

      bufferUnderrunCount: 0,

      queryCompletePayload: {
        response:
          'The final assistant response.',
      },
    };

    const payload =
      buildVoiceTelemetryPayload(
        timing,
      );

    assert.deepEqual(
      payload.llmFirstDelta,
      timing.firstDeltaPayload,
    );

    assert.deepEqual(
      payload.voicePipelineFirstAudio,
      timing.firstAudioPayload,
    );

    assert.deepEqual(
      payload.voicePipelinePlayback,
      timing.playbackPayload,
    );

    assert.deepEqual(
      payload.ttsGenerations,
      timing.ttsGenerations,
    );

    assert.equal(
      payload.bufferUnderrunCount,
      0,
    );

    assert.deepEqual(
      payload.queryComplete,
      timing.queryCompletePayload,
    );
  },
);


test(
  (
    'playback completion sends client '
    + 'telemetry exactly once'
  ),
  () => {
    const calls = [];

    const client = {
      sendClientTelemetry(
        requestId,
        payload,
      ) {
        calls.push({
          requestId,
          payload,
        });

        return true;
      },
    };

    const timing = {
      firstDeltaPayload: {
        seconds: 0.6051,
      },

      firstAudioPayload: {
        queryToFirstAudioSeconds:
          1.3268,
      },

      playbackPayload: {
        queryToPlaybackSeconds:
          1.3364,
      },

      ttsGenerations: [
        {
          generationSeconds:
            5.2455,
          audioDurationSeconds:
            6.4,
          realtimeFactor:
            0.8196,
        },
      ],

      bufferUnderrunCount: 1,

      queryCompletePayload: {
        response:
          'Completed response.',
      },
    };

    const sent =
      sendCompletedVoiceTelemetry({
        client,
        requestId: 'request-123',
        timing,
      });

    assert.equal(sent, true);
    assert.equal(calls.length, 1);

    assert.equal(
      calls[0].requestId,
      'request-123',
    );

    assert.equal(
      calls[0].payload
        .voicePipelineFirstAudio
        .queryToFirstAudioSeconds,
      1.3268,
    );

    assert.equal(
      calls[0].payload
        .voicePipelinePlayback
        .queryToPlaybackSeconds,
      1.3364,
    );

    assert.equal(
      calls[0].payload
        .ttsGenerations[0]
        .realtimeFactor,
      0.8196,
    );

    assert.equal(
      calls[0].payload
        .bufferUnderrunCount,
      1,
    );
  },
);


test(
  (
    'completed telemetry is not sent '
    + 'without timing data'
  ),
  () => {
    let callCount = 0;

    const client = {
      sendClientTelemetry() {
        callCount += 1;
        return true;
      },
    };

    const sent =
      sendCompletedVoiceTelemetry({
        client,
        requestId: 'request-123',
        timing: null,
      });

    assert.equal(sent, false);
    assert.equal(callCount, 0);
  },
);
