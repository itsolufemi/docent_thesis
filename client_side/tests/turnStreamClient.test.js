import assert from 'node:assert/strict';
import test from 'node:test';

import {
  TurnStreamClient,
} from '../src/api/turnStreamClient.js';


globalThis.WebSocket = {
  OPEN: 1,
};


test(
  (
    'sendClientTelemetry sends a '
    + 'request-scoped telemetry message'
  ),
  () => {
    const sentMessages = [];
    const client =
      new TurnStreamClient();

    client.socket = {
      readyState: WebSocket.OPEN,

      send(message) {
        sentMessages.push(
          JSON.parse(message),
        );
      },
    };

    const payload = {
      voicePipelinePlayback: {
        queryToPlaybackSeconds:
          1.4044,
      },
      bufferUnderrunCount: 0,
    };

    assert.equal(
      client.sendClientTelemetry(
        'request-telemetry',
        payload,
      ),
      true,
    );

    assert.deepEqual(
      sentMessages,
      [
        {
          type: 'client_telemetry',
          request_id:
            'request-telemetry',
          payload,
        },
      ],
    );
  },
);


test(
  'cancelTurn sends a request-scoped cancellation message',
  () => {
    const sentMessages = [];
    const client = new TurnStreamClient();

    client.socket = {
      readyState: WebSocket.OPEN,
      send(message) {
        sentMessages.push(
          JSON.parse(message),
        );
      },
    };

    assert.equal(
      client.cancelTurn('request-123'),
      true,
    );
    assert.deepEqual(
      sentMessages,
      [
        {
          type: 'cancel_turn',
          request_id: 'request-123',
        },
      ],
    );
  },
);


test(
  'cancelTurn is ignored without an active socket',
  () => {
    const client = new TurnStreamClient();

    assert.equal(
      client.cancelTurn('request-123'),
      false,
    );
    assert.equal(
      client.cancelTurn(''),
      false,
    );
  },
);


test(
  'playback interruption sends the exact request correction',
  () => {
    const sentMessages = [];
    const client = new TurnStreamClient();
    client.conversationId = 'conversation-123';
    client.socket = {
      readyState: WebSocket.OPEN,
      send(message) {
        sentMessages.push(
          JSON.parse(message),
        );
      },
    };

    assert.equal(
      client.recordAssistantPlaybackInterrupted(
        'request-a',
        'A. [interrupted]',
      ),
      true,
    );
    assert.deepEqual(
      sentMessages,
      [
        {
          type:
            'assistant_playback_interrupted',
          request_id: 'request-a',
          payload: {
            conversation_id:
              'conversation-123',
            assistant_text:
              'A. [interrupted]',
          },
        },
      ],
    );
  },
);


test(
  'turn_cancelled is routed to its request callback',
  () => {
    const cancellations = [];
    const client = new TurnStreamClient({
      onTurnCancelled(event) {
        cancellations.push(event);
      },
    });

    client.handleMessage(
      JSON.stringify({
        type: 'turn_cancelled',
        request_id: 'request-123',
        payload: {
          reason: 'cancelled',
        },
      }),
    );

    assert.deepEqual(
      cancellations,
      [
        {
          requestId: 'request-123',
          payload: {
            reason: 'cancelled',
          },
        },
      ],
    );
  },
);


test(
  'confirmed acoustic turns are included in turn events',
  () => {
    const sentMessages = [];
    const client = new TurnStreamClient();

    client.socket = {
      readyState: WebSocket.OPEN,
      send(message) {
        sentMessages.push(
          JSON.parse(message),
        );
      },
    };

    client.sendTurnEvent({
      partialUtterance: 'Tell me about it.',
      isSpeechActive: false,
      silenceDurationMs: 500,
      assistantWasSpeaking: false,
      turnCompletionConfirmed: true,
    });

    assert.equal(
      sentMessages[0].payload
        .turn_completion_confirmed,
      true,
    );
  },
);


test(
  'turn events carry provisional playback interruption context',
  () => {
    const sentMessages = [];
    const client = new TurnStreamClient();

    client.socket = {
      readyState: WebSocket.OPEN,
      send(message) {
        sentMessages.push(
          JSON.parse(message),
        );
      },
    };

    client.sendTurnEvent({
      partialUtterance: 'by Thomas Sully',
      isSpeechActive: false,
      silenceDurationMs: 500,
      assistantWasSpeaking: true,
      interruptedRequestId: 'request-a',
      interruptedAssistantText:
        'A. [interrupted]',
    });

    assert.equal(
      sentMessages[0].payload
        .interrupted_request_id,
      'request-a',
    );
    assert.equal(
      sentMessages[0].payload
        .interrupted_assistant_text,
      'A. [interrupted]',
    );
  },
);
