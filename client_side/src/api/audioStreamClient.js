const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  'http://127.0.0.1:8000';


function buildWebSocketUrl() {
  const url = new URL(API_BASE_URL);
  const websocketProtocol =
    url.protocol === 'https:' ? 'wss:' : 'ws:';

  return (
    `${websocketProtocol}//${url.host}` +
    '/api/audio/stream'
  );
}


export class AudioStreamClient {
  constructor({
    onOpen,
    onMessage,
    onError,
    onClose,
  } = {}) {
    this.socket = null;
    this.connectionPromise = null;

    this.onOpen = onOpen;
    this.onMessage = onMessage;
    this.onError = onError;
    this.onClose = onClose;
  }

  connect() {
    if (
      this.socket?.readyState === WebSocket.OPEN
    ) {
      return Promise.resolve();
    }

    if (
      this.socket?.readyState === WebSocket.CONNECTING &&
      this.connectionPromise
    ) {
      return this.connectionPromise;
    }

    this.connectionPromise = new Promise((resolve, reject) => {
      const socket = new WebSocket(buildWebSocketUrl());

      socket.binaryType = 'arraybuffer';
      this.socket = socket;

      socket.onopen = () => {
        this.connectionPromise = null;
        this.onOpen?.();
        resolve();
      };

      socket.onmessage = (event) => {
        if (typeof event.data !== 'string') {
          return;
        }

        try {
          const message = JSON.parse(event.data);
          this.onMessage?.(message);
        } catch (error) {
          console.error(
            'Invalid audio WebSocket message:',
            error,
          );
        }
      };

      socket.onerror = (event) => {
        this.connectionPromise = null;
        this.onError?.(event);
        reject(
          new Error(
            'Could not connect to audio WebSocket.',
          ),
        );
      };

      socket.onclose = (event) => {
        this.connectionPromise = null;
        this.onClose?.(event);
      };
    });

    return this.connectionPromise;
  }

  sendControl(type, payload = {}) {
    if (
      !this.socket ||
      this.socket.readyState !== WebSocket.OPEN
    ) {
      throw new Error(
        'Audio WebSocket is not connected.',
      );
    }

    this.socket.send(
      JSON.stringify({
        type,
        payload,
      }),
    );
  }

  startStream({
    sampleRate = 16000,
    channels = 1,
  } = {}) {
    this.sendControl(
      'start_audio',
      {
        sample_rate: sampleRate,
        channels,
        sample_format: 'pcm_s16le',
      },
    );
  }

  sendChunk(chunk) {
    if (
      !this.socket ||
      this.socket.readyState !== WebSocket.OPEN
    ) {
      return false;
    }

    if (chunk instanceof Uint8Array) {
      const chunkBytes = chunk.buffer.slice(
        chunk.byteOffset,
        chunk.byteOffset + chunk.byteLength,
      );
      this.socket.send(chunkBytes);
      return true;
    }

    if (chunk instanceof ArrayBuffer) {
      this.socket.send(chunk);
      return true;
    }

    throw new TypeError(
      'Audio chunk must be Uint8Array or ArrayBuffer.',
    );
  }

  stopStream() {
    this.sendControl('stop_audio');
  }

  cancelStream() {
    this.sendControl('cancel_audio');
  }

  close() {
    if (!this.socket) {
      return;
    }

    this.socket.close();
    this.socket = null;
    this.connectionPromise = null;
  }
}
