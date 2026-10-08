import assert from 'node:assert/strict';
import test from 'node:test';

import {
  TtsStreamClient,
} from '../src/api/ttsStreamClient.js';


function installFakeWebSocket() {
  const originalWebSocket = globalThis.WebSocket;
  const sockets = [];

  class FakeWebSocket {
    constructor(url) {
      this.url = url;
      this.binaryType = null;
      this.sentMessages = [];
      sockets.push(this);
    }

    send(message) {
      this.sentMessages.push(JSON.parse(message));
    }

    close() {}
  }

  globalThis.WebSocket = FakeWebSocket;

  return {
    sockets,
    restore() {
      if (originalWebSocket === undefined) {
        delete globalThis.WebSocket;
      } else {
        globalThis.WebSocket = originalWebSocket;
      }
    },
  };
}


function sendReady(socket) {
  socket.onopen();
  socket.onmessage({
    data: JSON.stringify({
      type: 'tts_ready',
      payload: {
        provider: 'fake',
        sample_rate: 24000,
      },
    }),
  });
}


test('manual close notifies lifecycle', () => {
  let closeEvent = null;
  let socketClosed = false;
  const client = new TtsStreamClient({
    onClose: (event) => {
      closeEvent = event;
    },
  });
  client.socket = {
    onmessage: () => {},
    onerror: () => {},
    onclose: () => {},
    close: () => {
      socketClosed = true;
    },
  };

  client.close();

  assert.equal(socketClosed, true);
  assert.equal(client.socket, null);
  assert.equal(closeEvent.reason, 'client_closed');
});


test(
  'two syntheses reuse one socket and preserve audio timing',
  async () => {
    const fakeWebSocket = installFakeWebSocket();
    const firstAudioTimings = [];
    const audioChunks = [];

    try {
      const client = new TtsStreamClient();
      const firstSynthesis = client.synthesise({
        synthesisId: 'first',
        text: 'Hello from Docent.',
        onFirstAudio: (timing) => {
          firstAudioTimings.push(timing);
        },
        onAudioChunk: (chunk) => {
          audioChunks.push(chunk);
        },
      });
      const socket = fakeWebSocket.sockets[0];
      sendReady(socket);
      await new Promise((resolve) => setTimeout(resolve, 0));

      assert.equal(fakeWebSocket.sockets.length, 1);
      assert.equal(
        socket.sentMessages[0].payload.synthesis_id,
        'first',
      );

      socket.onmessage({
        data: JSON.stringify({
          type: 'tts_chunk',
          payload: {
            synthesis_id: 'first',
            chunk_index: 0,
            first_chunk: true,
            request_to_first_chunk_seconds: 0.1234,
          },
        }),
      });
      socket.onmessage({
        data: new Int16Array([-32768, 0, 32767]).buffer,
      });
      socket.onmessage({
        data: JSON.stringify({
          type: 'tts_complete',
          payload: { synthesis_id: 'first' },
        }),
      });
      await firstSynthesis;

      const secondSynthesis = client.synthesise({
        synthesisId: 'second',
        text: 'A second sentence.',
      });
      await new Promise((resolve) => setTimeout(resolve, 0));

      assert.equal(fakeWebSocket.sockets.length, 1);
      assert.equal(
        socket.sentMessages[1].payload.synthesis_id,
        'second',
      );

      socket.onmessage({
        data: JSON.stringify({
          type: 'tts_complete',
          payload: { synthesis_id: 'second' },
        }),
      });
      await secondSynthesis;

      assert.equal(firstAudioTimings.length, 1);
      assert.equal(
        firstAudioTimings[0]
          .serverRequestToFirstChunkSeconds,
        0.1234,
      );
      assert.equal(audioChunks.length, 1);
      assert.deepEqual(
        Array.from(audioChunks[0].samples),
        [-1, 0, 1],
      );
    } finally {
      fakeWebSocket.restore();
    }
  },
);


test('cancel keeps the persistent socket open', async () => {
  const fakeWebSocket = installFakeWebSocket();

  try {
    const client = new TtsStreamClient();
    const connection = client.connect();
    const socket = fakeWebSocket.sockets[0];
    sendReady(socket);
    await connection;

    const synthesis = client.synthesise({
      synthesisId: 'cancel-me',
      text: 'Cancel this.',
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    client.cancel('cancel-me');

    assert.equal(fakeWebSocket.sockets.length, 1);
    assert.equal(
      socket.sentMessages.at(-1).type,
      'cancel',
    );

    socket.onmessage({
      data: JSON.stringify({
        type: 'tts_cancelled',
        payload: { synthesis_id: 'cancel-me' },
      }),
    });

    const result = await synthesis;
    assert.equal(result.cancelled, true);
    assert.equal(client.socket, socket);
  } finally {
    fakeWebSocket.restore();
  }
});
