const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';


export async function sendTurnBufferEvent({
  partialUtterance,
  isSpeechActive,
  silenceDurationMs,
  assistantWasSpeaking = false,
  debug = false,
}) {
  const response = await fetch(
    `${API_BASE_URL}/api/conversation/turn-buffer/event`,
    {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        partial_utterance: partialUtterance,
        is_speech_active: isSpeechActive,
        silence_duration_ms: silenceDurationMs,
        assistant_was_speaking:
          assistantWasSpeaking,
        debug,
      }),
    },
  );

  if (!response.ok) {
    let errorMessage =
      `Turn processing failed with status ${response.status}`;

    try {
      const errorBody = await response.json();

      if (errorBody?.detail) {
        errorMessage = `${errorMessage}: ${JSON.stringify(errorBody.detail)}`;
      }
    } catch {
      // Keep the status-based message when the server response is not JSON.
    }

    throw new Error(errorMessage);
  }

  return response.json();
}
