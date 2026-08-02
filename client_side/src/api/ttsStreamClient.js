const API_BASE_URL =
  import.meta.env?.VITE_API_BASE_URL ??
  'http://127.0.0.1:8000';


function toWebSocketUrl(httpUrl) {
  const url = new URL(httpUrl);

  url.protocol =
    url.protocol === 'https:'
      ? 'wss:'
      : 'ws:';

  return url.toString();
}


function pcm16ToFloat32(arrayBuffer) {
  const pcm16 = new Int16Array(
    arrayBuffer,
  );
  const float32 = new Float32Array(
    pcm16.length,
  );

  for (
    let index = 0;
    index < pcm16.length;
    index += 1
  ) {
    const sample = pcm16[index];

    float32[index] =
      sample < 0
        ? sample / 32768
        : sample / 32767;
  }

  return float32;
}


export class TtsStreamClient {
  constructor({
    onStarted,
    onFirstAudio,
    onAudioChunk,
    onComplete,
    onError,
    onClose,
  } = {}) {
    this.socket = null;
    this.pendingChunkMetadata = null;

    this.onStarted = onStarted;
    this.onFirstAudio = onFirstAudio;
    this.onAudioChunk = onAudioChunk;
    this.onComplete = onComplete;
    this.onError = onError;
    this.onClose = onClose;
  }

  connect({
    text,
    voiceName = null,
    languageCode = null,
  }) {
    const connectStartedAt =
      performance.now();

    let socketOpenedAt = null;
    let requestSentAt = null;
    let firstAudioReceived = false;

    return new Promise(
      (resolve, reject) => {
        const socketUrl =
          toWebSocketUrl(
            `${API_BASE_URL}/api/tts/stream`,
          );
        const socket = new WebSocket(
          socketUrl,
        );

        socket.binaryType = 'arraybuffer';
        this.socket = socket;

        socket.onopen = () => {
          socketOpenedAt = performance.now();

          socket.send(
            JSON.stringify({
              type: 'synthesise',
              payload: {
                text,
                voice_name: voiceName,
                language_code:
                  languageCode,
              },
            }),
          );

          requestSentAt = performance.now();

          resolve();
        };

        socket.onmessage = (event) => {
          if (
            event.data instanceof
            ArrayBuffer
          ) {
            const audioReceivedAt =
              performance.now();

            const chunkMetadata =
              this.pendingChunkMetadata;

            if (!firstAudioReceived) {
              firstAudioReceived = true;

              this.onFirstAudio?.({
                connectSeconds: (
                  socketOpenedAt !== null
                    ? (
                        socketOpenedAt
                        - connectStartedAt
                      ) / 1000
                    : null
                ),
                requestToFirstAudioSeconds: (
                  requestSentAt !== null
                    ? (
                        audioReceivedAt
                        - requestSentAt
                      ) / 1000
                    : null
                ),
                connectToFirstAudioSeconds: (
                  audioReceivedAt
                  - connectStartedAt
                ) / 1000,
                serverRequestToFirstChunkSeconds:
                  chunkMetadata
                    ?.request_to_first_chunk_seconds
                    ?? null,
              });
            }

            const samples =
              pcm16ToFloat32(
                event.data,
              );

            this.onAudioChunk?.({
              metadata: chunkMetadata,
              samples,
            });

            this.pendingChunkMetadata =
              null;

            return;
          }

          let message;

          try {
            message = JSON.parse(
              event.data,
            );
          } catch {
            this.onError?.(
              new Error(
                'TTS stream returned invalid JSON.',
              ),
            );
            return;
          }

          switch (message.type) {
            case 'tts_started':
              this.onStarted?.(
                message.payload,
              );
              break;

            case 'tts_chunk':
              this.pendingChunkMetadata =
                message.payload;
              break;

            case 'tts_complete':
              this.onComplete?.(
                message.payload,
              );
              break;

            case 'tts_error':
              this.onError?.(
                new Error(
                  message.payload?.detail ??
                  'Unknown TTS stream error.',
                ),
              );
              break;

            default:
              console.warn(
                'Unknown TTS message:',
                message,
              );
          }
        };

        socket.onerror = () => {
          const error = new Error(
            'The TTS WebSocket failed.',
          );

          this.onError?.(error);
          reject(error);
        };

        socket.onclose = () => {
          if (this.socket === socket) {
            this.socket = null;
          }

          this.onClose?.();
        };
      },
    );
  }

  close() {
    if (!this.socket) {
      return;
    }

    const onClose = this.onClose;
    const socket = this.socket;

    this.socket.onmessage = null;
    this.socket.onerror = null;
    this.socket.onclose = null;

    try {
      socket.close();
    } catch {
      // The socket may already be closed.
    }

    this.socket = null;
    this.pendingChunkMetadata = null;

    onClose?.({
      code: 1000,
      reason: 'client_closed',
      wasClean: true,
    });
  }
}
