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


export class TurnStreamClient {
  constructor({
    onReady,
    onTurnEvaluated,
    onUtteranceClassified,
    onQueryStarted,
    onResponseStarted,
    onResponseFirstDelta,
    onResponseDelta,
    onToolCallStarted,
    onToolCallComplete,
    onResponseComplete,
    onTurnCancelled,
    onQueryComplete,
    onError,
    onClose,
  } = {}) {
    this.socket = null;
    this.onReady = onReady;
    this.onTurnEvaluated =
      onTurnEvaluated;
    this.onUtteranceClassified =
      onUtteranceClassified;
    this.onQueryStarted =
      onQueryStarted;
    this.onResponseStarted =
      onResponseStarted;
    this.onResponseFirstDelta =
      onResponseFirstDelta;
    this.onResponseDelta =
      onResponseDelta;
    this.onToolCallStarted =
      onToolCallStarted;
    this.onToolCallComplete =
      onToolCallComplete;
    this.onResponseComplete =
      onResponseComplete;
    this.onTurnCancelled =
      onTurnCancelled;
    this.onQueryComplete =
      onQueryComplete;
    this.onError = onError;
    this.onClose = onClose;
  }

  async connect() {
    if (
      this.socket?.readyState ===
      WebSocket.OPEN
    ) {
      return;
    }

    const websocketUrl =
      toWebSocketUrl(
        `${API_BASE_URL}/api/conversation/turn-buffer/stream`,
      );

    await new Promise(
      (resolve, reject) => {
        const socket =
          new WebSocket(websocketUrl);

        this.socket = socket;

        socket.onopen = () => {
          resolve();
        };

        socket.onerror = () => {
          reject(
            new Error(
              'Turn stream connection failed.',
            ),
          );
        };

        socket.onmessage = (event) => {
          this.handleMessage(event.data);
        };

        socket.onclose = (event) => {
          if (this.socket === socket) {
            this.socket = null;
          }

          this.onClose?.(event);
        };
      },
    );
  }

  handleMessage(rawMessage) {
    let message;

    try {
      message = JSON.parse(rawMessage);
    } catch {
      this.onError?.(
        new Error(
          'Turn stream returned invalid JSON.',
        ),
      );
      return;
    }

    const payload =
      message.payload ?? {};

    switch (message.type) {
      case 'turn_stream_ready':
        this.onReady?.(payload);
        break;

      case 'turn_evaluated':
        this.onTurnEvaluated?.({
          requestId:
            message.request_id,
          payload,
        });
        break;

      case 'utterance_classified':
        this.onUtteranceClassified?.({
          requestId:
            message.request_id,
          payload,
        });
        break;

      case 'query_started':
        this.onQueryStarted?.({
          requestId:
            message.request_id,
          payload,
        });
        break;

      case 'response_started':
        this.onResponseStarted?.({
          requestId:
            message.request_id,
          payload,
        });
        break;

      case 'response_first_delta':
        this.onResponseFirstDelta?.({
          requestId:
            message.request_id,
          payload,
        });
        break;

      case 'response_delta':
        this.onResponseDelta?.({
          requestId:
            message.request_id,
          payload,
        });
        break;

      case 'tool_call_started':
        this.onToolCallStarted?.({
          requestId:
            message.request_id,
          payload,
        });
        break;

      case 'tool_call_complete':
        this.onToolCallComplete?.({
          requestId:
            message.request_id,
          payload,
        });
        break;

      case 'response_complete':
        this.onResponseComplete?.({
          requestId:
            message.request_id,
          payload,
        });
        break;

      case 'turn_cancelled':
        this.onTurnCancelled?.({
          requestId:
            message.request_id,
          payload,
        });
        break;

      case 'query_complete':
        this.onQueryComplete?.({
          requestId:
            message.request_id,
          payload,
        });
        break;

      case 'turn_error':
        this.onError?.(
          new Error(
            payload.detail ??
            'Turn processing failed.',
          ),
          message.request_id,
        );
        break;

      default:
        break;
    }
  }

  sendTurnEvent({
    partialUtterance,
    isSpeechActive,
    silenceDurationMs,
    assistantWasSpeaking,
    turnCompletionConfirmed = false,
    debug = false,
  }) {
    if (
      this.socket?.readyState !==
      WebSocket.OPEN
    ) {
      throw new Error(
        'Turn stream is not connected.',
      );
    }

    const requestId =
      crypto.randomUUID();

    this.socket.send(
      JSON.stringify({
        type: 'turn_event',
        request_id: requestId,
        payload: {
          partial_utterance:
            partialUtterance,
          is_speech_active:
            isSpeechActive,
          silence_duration_ms:
            silenceDurationMs,
          assistant_was_speaking:
            assistantWasSpeaking,
          turn_completion_confirmed:
            turnCompletionConfirmed,
          debug,
        },
      }),
    );

    return requestId;
  }

  cancelTurn(requestId) {
    if (
      !requestId ||
      this.socket?.readyState !==
        WebSocket.OPEN
    ) {
      return false;
    }

    this.socket.send(
      JSON.stringify({
        type: 'cancel_turn',
        request_id: requestId,
      }),
    );

    return true;
  }

  close() {
    const socket = this.socket;

    this.socket = null;

    if (
      socket &&
      socket.readyState <
        WebSocket.CLOSING
    ) {
      socket.close();
    }
  }
}
