import assert from 'node:assert/strict';
import test from 'node:test';

import {
  TurnStreamClient,
} from '../src/api/turnStreamClient.js';


globalThis.WebSocket = {
  OPEN: 1,
};


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
