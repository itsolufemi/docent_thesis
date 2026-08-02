const API_BASE_URL =
  import.meta.env?.VITE_API_BASE_URL ??
  'http://127.0.0.1:8000';


function toWebSocketUrl(httpUrl) {
  const url = new URL(httpUrl);
  url.protocol =
    url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}


function pcm16ToFloat32(arrayBuffer) {
  const pcm16 = new Int16Array(arrayBuffer);
  const float32 = new Float32Array(pcm16.length);

  for (let index = 0; index < pcm16.length; index += 1) {
    const sample = pcm16[index];
    float32[index] =
      sample < 0 ? sample / 32768 : sample / 32767;
  }

  return float32;
}


function createSynthesisId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }

  return `tts-${Date.now()}-${Math.random()}`;
}


export class TtsStreamClient {
  constructor({
    onReady,
    onError,
    onClose,
  } = {}) {
    this.socket = null;
    this.ready = false;
    this.readyMetadata = null;
    this.connectPromise = null;
    this.connectStartedAt = null;
    this.socketOpenedAt = null;
    this.pendingChunkMetadata = null;
    this.requests = new Map();
    this.onReady = onReady;
    this.onError = onError;
    this.onClose = onClose;
  }

  connect() {
    if (this.ready && this.socket) {
      return Promise.resolve(this.readyMetadata);
    }

    if (this.connectPromise) {
      return this.connectPromise;
    }

    this.connectStartedAt = performance.now();
    const socket = new WebSocket(
      toWebSocketUrl(
        `${API_BASE_URL}/api/tts/stream`,
      ),
    );
    socket.binaryType = 'arraybuffer';
    this.socket = socket;

    this.connectPromise = new Promise(
      (resolve, reject) => {
        socket.onopen = () => {
          this.socketOpenedAt = performance.now();
        };

        socket.onmessage = (event) => {
          this.handleMessage(event, resolve);
        };

        socket.onerror = () => {
          if (this.socket !== socket) {
            return;
          }

          const error = new Error(
            'The TTS WebSocket failed.',
          );
          this.socket = null;
          this.ready = false;
          this.readyMetadata = null;
          this.connectPromise = null;
          this.onError?.(error);
          reject(error);
          this.rejectAll(error);
        };

        socket.onclose = (event) => {
          if (this.socket !== socket) {
            return;
          }

          this.socket = null;
          this.ready = false;
          this.readyMetadata = null;
          this.connectPromise = null;

          const error = new Error(
            'TTS stream closed before completion.',
          );
          reject(error);
          this.rejectAll(error);
          this.onClose?.(event);
        };
      },
    );

    return this.connectPromise;
  }

  handleMessage(event, resolveConnection) {
    if (event.data instanceof ArrayBuffer) {
      const metadata = this.pendingChunkMetadata;
      this.pendingChunkMetadata = null;

      if (!metadata) {
        return;
      }

      const request = this.requests.get(
        metadata.synthesis_id,
      );

      if (!request) {
        return;
      }

      const audioReceivedAt = performance.now();

      if (!request.firstAudioReceived) {
        request.firstAudioReceived = true;
        request.onFirstAudio?.({
          connectionReused: request.connectionReused,
          connectSeconds: request.connectionReused
            ? 0
            : (
                this.socketOpenedAt
                - this.connectStartedAt
              ) / 1000,
          requestToFirstAudioSeconds:
            (
              audioReceivedAt
              - request.requestSentAt
            ) / 1000,
          connectToFirstAudioSeconds:
            (
              audioReceivedAt
              - this.connectStartedAt
            ) / 1000,
          serverRequestToFirstChunkSeconds:
            metadata
              .request_to_first_chunk_seconds ?? null,
        });
      }

      const samples = pcm16ToFloat32(event.data);
      request.onAudioChunk?.({ metadata, samples });
      return;
    }

    let message;

    try {
      message = JSON.parse(event.data);
    } catch {
      this.onError?.(
        new Error('TTS stream returned invalid JSON.'),
      );
      return;
    }

    const payload = message.payload ?? {};
    const synthesisId = payload.synthesis_id;
    const request = synthesisId
      ? this.requests.get(synthesisId)
      : null;

    switch (message.type) {
      case 'tts_ready':
        this.ready = true;
        this.readyMetadata = payload;
        this.onReady?.(payload);
        resolveConnection?.(payload);
        break;

      case 'tts_started':
        request?.onStarted?.(payload);
        break;

      case 'tts_chunk':
        this.pendingChunkMetadata = payload;
        break;

      case 'tts_complete':
        if (
          this.pendingChunkMetadata?.synthesis_id ===
          synthesisId
        ) {
          this.pendingChunkMetadata = null;
        }
        request?.onComplete?.(payload);
        request?.resolve(payload);
        this.requests.delete(synthesisId);
        break;

      case 'tts_cancelled':
        if (
          this.pendingChunkMetadata?.synthesis_id ===
          synthesisId
        ) {
          this.pendingChunkMetadata = null;
        }
        request?.onCancelled?.(payload);
        request?.resolve({ ...payload, cancelled: true });
        this.requests.delete(synthesisId);
        break;

      case 'tts_error': {
        const error = new Error(
          payload.detail ?? 'Unknown TTS stream error.',
        );

        if (request) {
          if (
            this.pendingChunkMetadata?.synthesis_id ===
            synthesisId
          ) {
            this.pendingChunkMetadata = null;
          }
          request.onError?.(error);
          request.reject(error);
          this.requests.delete(synthesisId);
        } else {
          this.onError?.(error);
        }
        break;
      }

      default:
        console.warn('Unknown TTS message:', message);
    }
  }

  async synthesise({
    text,
    voiceName = null,
    languageCode = null,
    synthesisId = createSynthesisId(),
    onStarted,
    onFirstAudio,
    onAudioChunk,
    onComplete,
    onCancelled,
    onError,
  }) {
    const connectionReused = this.ready && Boolean(this.socket);
    await this.connect();

    return new Promise((resolve, reject) => {
      const requestSentAt = performance.now();
      this.requests.set(synthesisId, {
        resolve,
        reject,
        onStarted,
        onFirstAudio,
        onAudioChunk,
        onComplete,
        onCancelled,
        onError,
        requestSentAt,
        connectionReused,
        firstAudioReceived: false,
      });
      this.socket.send(JSON.stringify({
        type: 'synthesise',
        payload: {
          synthesis_id: synthesisId,
          text,
          voice_name: voiceName,
          language_code: languageCode,
        },
      }));
    });
  }

  cancel(synthesisId) {
    if (!this.ready || !this.socket || !synthesisId) {
      return;
    }

    this.socket.send(JSON.stringify({
      type: 'cancel',
      payload: { synthesis_id: synthesisId },
    }));
  }

  rejectAll(error) {
    for (const request of this.requests.values()) {
      request.onError?.(error);
      request.reject(error);
    }

    this.requests.clear();
  }

  close() {
    if (!this.socket) {
      return;
    }

    const socket = this.socket;
    socket.onmessage = null;
    socket.onerror = null;
    socket.onclose = null;

    try {
      socket.close();
    } catch {
      // The socket may already be closed.
    }

    this.socket = null;
    this.ready = false;
    this.readyMetadata = null;
    this.connectPromise = null;
    this.pendingChunkMetadata = null;
    this.rejectAll(new Error('TTS client closed.'));
    this.onClose?.({
      code: 1000,
      reason: 'client_closed',
      wasClean: true,
    });
  }
}
