import assert from 'node:assert/strict';
import test from 'node:test';

import {
  AudioStreamClient,
} from '../src/api/audioStreamClient.js';


globalThis.WebSocket = {
  OPEN: 1,
};


function connectedClient() {
  const messages = [];
  const client = new AudioStreamClient();

  client.socket = {
    readyState: WebSocket.OPEN,
    send(message) {
      messages.push(JSON.parse(message));
    },
  };
  client.currentSegmentId = 'segment-1';

  return { client, messages };
}


test(
  'candidate evaluation preserves the active segment',
  () => {
    const { client, messages } =
      connectedClient();

    client.evaluateCandidate({
      candidateId: 3,
      silenceDurationMs: 500,
    });

    assert.equal(
      client.currentSegmentId,
      'segment-1',
    );
    assert.deepEqual(messages[0], {
      type: 'candidate_segment',
      payload: {
        segment_id: 'segment-1',
        candidate_id: 3,
        silence_duration_ms: 500,
      },
    });
  },
);


test(
  'speech resumption invalidates without closing the segment',
  () => {
    const { client, messages } =
      connectedClient();

    client.notifySpeechResumed({
      candidateId: 4,
    });

    assert.equal(
      client.currentSegmentId,
      'segment-1',
    );
    assert.equal(
      messages[0].type,
      'speech_resumed',
    );
  },
);


test(
  'accepted candidates detach the segment for transcription',
  () => {
    const { client, messages } =
      connectedClient();

    const segmentId = client.finaliseSegment({
      candidateId: 5,
      silenceDurationMs: 500,
      forcedFinalisation: false,
    });

    assert.equal(segmentId, 'segment-1');
    assert.equal(client.currentSegmentId, null);
    assert.deepEqual(messages[0].payload, {
      segment_id: 'segment-1',
      silence_duration_ms: 500,
      candidate_id: 5,
      forced_finalisation: false,
    });
  },
);
