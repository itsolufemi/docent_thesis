import assert from 'node:assert/strict';
import test from 'node:test';

import {
  TtsStreamClient,
} from '../src/api/ttsStreamClient.js';


function installFakeWebSocket() {
  const originalWebSocket =
    globalThis.WebSocket;
  const sockets = [];

  class FakeWebSocket {
    constructor(url) {
      this.url = url;
      this.binaryType = null;
      this.sentMessages = [];
      sockets.push(this);
    }

    send(message) {
      this.sentMessages.push(message);
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
        globalThis.WebSocket =
          originalWebSocket;
      }
    },
  };
}


test(
  'manual close notifies pending stream lifecycle',
  () => {
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
    assert.equal(
      closeEvent.reason,
      'client_closed',
    );
  },
);


test(
  'first audio timing fires once and preserves chunk data',
  async () => {
    const fakeWebSocket =
      installFakeWebSocket();
    const firstAudioTimings = [];
    const audioChunks = [];

    try {
      const client = new TtsStreamClient({
        onFirstAudio: (timing) => {
          firstAudioTimings.push(timing);
        },
        onAudioChunk: (chunk) => {
          audioChunks.push(chunk);
        },
      });
      const connection = client.connect({
        text: 'Hello from Docent.',
      });
      const socket = fakeWebSocket.sockets[0];

      socket.onopen();
      await connection;

      socket.onmessage({
        data: JSON.stringify({
          type: 'tts_chunk',
          payload: {
            chunk_index: 0,
            first_chunk: true,
            request_to_first_chunk_seconds:
              0.1234,
          },
        }),
      });
      socket.onmessage({
        data: new Int16Array([
          -32768,
          0,
          32767,
        ]).buffer,
      });

      socket.onmessage({
        data: JSON.stringify({
          type: 'tts_chunk',
          payload: {
            chunk_index: 1,
            first_chunk: false,
            request_to_first_chunk_seconds:
              null,
          },
        }),
      });
      socket.onmessage({
        data: new Int16Array([100]).buffer,
      });

      assert.equal(
        firstAudioTimings.length,
        1,
      );
      assert.ok(
        firstAudioTimings[0]
          .connectSeconds >= 0,
      );
      assert.ok(
        firstAudioTimings[0]
          .requestToFirstAudioSeconds >= 0,
      );
      assert.ok(
        firstAudioTimings[0]
          .connectToFirstAudioSeconds >= 0,
      );
      assert.equal(
        firstAudioTimings[0]
          .serverRequestToFirstChunkSeconds,
        0.1234,
      );

      assert.equal(audioChunks.length, 2);
      assert.equal(
        audioChunks[0].metadata.chunk_index,
        0,
      );
      assert.equal(
        audioChunks[1].metadata.chunk_index,
        1,
      );
      assert.deepEqual(
        Array.from(audioChunks[0].samples),
        [-1, 0, 1],
      );
    } finally {
      fakeWebSocket.restore();
    }
  },
);
