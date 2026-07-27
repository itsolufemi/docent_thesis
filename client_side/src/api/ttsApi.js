const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  'http://127.0.0.1:8000';


export async function synthesiseSpeech({
  text,
  voiceName = null,
  languageCode = null,
  signal,
}) {
  const cleanedText = text?.trim();

  if (!cleanedText) {
    throw new Error(
      'Cannot synthesise an empty response.',
    );
  }

  const response = await fetch(
    `${API_BASE_URL}/api/tts/synthesise`,
    {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text: cleanedText,
        voice_name: voiceName,
        language_code: languageCode,
      }),
      signal,
    },
  );

  if (!response.ok) {
    let detail =
      'TTS request failed with status ' +
      `${response.status}.`;

    try {
      const payload = await response.json();

      if (payload?.detail) {
        detail = payload.detail;
      }
    } catch {
      // The error response was not JSON.
    }

    throw new Error(detail);
  }

  const audioData = await response.arrayBuffer();

  return {
    audioData,
    metadata: {
      voice:
        response.headers.get('X-TTS-Voice'),
      language:
        response.headers.get(
          'X-TTS-Language',
        ),
      sampleRate: Number(
        response.headers.get(
          'X-TTS-Sample-Rate',
        ) ?? 0,
      ),
      characterCount: Number(
        response.headers.get(
          'X-TTS-Characters',
        ) ?? 0,
      ),
      generationSeconds: Number(
        response.headers.get(
          'X-TTS-Generation-Seconds',
        ) ?? 0,
      ),
    },
  };
}
