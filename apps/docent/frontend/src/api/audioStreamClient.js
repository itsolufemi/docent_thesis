const API_BASE_URL =
  import.meta.env?.VITE_API_BASE_URL ??
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
    this.currentSegmentId = null;
    this.nextSegmentNumber = 1;

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

          if (
            message.type === 'audio_segment_cancelled' &&
            message.payload?.segment_id ===
              this.currentSegmentId
          ) {
            this.currentSegmentId = null;
          }

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

  startSegment({
    segmentId,
    sampleRate = 16000,
    channels = 1,
  } = {}) {
    if (this.currentSegmentId) {
      throw new Error(
        'An audio segment is already active.',
      );
    }

    const nextSegmentId =
      segmentId ??
      `segment-${this.nextSegmentNumber}`;

    this.sendControl(
      'start_segment',
      {
        segment_id: nextSegmentId,
        sample_rate: sampleRate,
        channels,
        sample_format: 'pcm_s16le',
      },
    );

    this.currentSegmentId = nextSegmentId;
    this.nextSegmentNumber += 1;

    return nextSegmentId;
  }

  sendChunk(chunk) {
    if (
      !this.socket ||
      this.socket.readyState !== WebSocket.OPEN
    ) {
      return false;
    }

    if (!this.currentSegmentId) {
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

  finaliseSegment({
    silenceDurationMs = 500,
    candidateId = null,
    forcedFinalisation = false,
  } = {}) {
    if (!this.currentSegmentId) {
      throw new Error(
        'No active audio segment exists.',
      );
    }

    const segmentId = this.currentSegmentId;

    this.sendControl(
      'finalise_segment',
      {
        segment_id: segmentId,
        silence_duration_ms: silenceDurationMs,
        candidate_id: candidateId,
        forced_finalisation: forcedFinalisation,
      },
    );

    this.currentSegmentId = null;
    return segmentId;
  }

  evaluateCandidate({
    candidateId,
    silenceDurationMs = 500,
  }) {
    if (!this.currentSegmentId) {
      throw new Error(
        'No active audio segment exists.',
      );
    }

    this.sendControl(
      'candidate_segment',
      {
        segment_id: this.currentSegmentId,
        candidate_id: candidateId,
        silence_duration_ms: silenceDurationMs,
      },
    );

    return this.currentSegmentId;
  }

  notifySpeechResumed({
    candidateId = null,
  } = {}) {
    if (!this.currentSegmentId) {
      return null;
    }

    this.sendControl(
      'speech_resumed',
      {
        segment_id: this.currentSegmentId,
        candidate_id: candidateId,
      },
    );

    return this.currentSegmentId;
  }

  cancelSegment() {
    if (!this.currentSegmentId) {
      return null;
    }

    const segmentId = this.currentSegmentId;

    this.sendControl(
      'cancel_segment',
      {
        segment_id: segmentId,
      },
    );

    this.currentSegmentId = null;
    return segmentId;
  }

  close() {
    if (!this.socket) {
      return;
    }

    this.socket.close();
    this.socket = null;
    this.connectionPromise = null;
    this.currentSegmentId = null;
  }
}
