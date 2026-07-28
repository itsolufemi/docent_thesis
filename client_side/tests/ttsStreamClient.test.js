import assert from 'node:assert/strict';
import test from 'node:test';

import {
  TtsStreamClient,
} from '../src/api/ttsStreamClient.js';


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
