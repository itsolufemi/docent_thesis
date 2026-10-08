export function buildVoiceTelemetryPayload(
  timing,
) {
  if (!timing) {
    return null;
  }

  return {
    llmFirstDelta:
      timing.firstDeltaPayload ?? null,

    voicePipelineFirstAudio:
      timing.firstAudioPayload ?? null,

    voicePipelinePlayback:
      timing.playbackPayload ?? null,

    ttsGenerations:
      timing.ttsGenerations ?? [],

    bufferUnderrunCount:
      timing.bufferUnderrunCount ?? 0,

    queryComplete:
      timing.queryCompletePayload ?? null,
  };
}


export function sendCompletedVoiceTelemetry({
  client,
  requestId,
  timing,
}) {
  const payload =
    buildVoiceTelemetryPayload(
      timing,
    );

  if (
    !client ||
    !requestId ||
    !payload
  ) {
    return false;
  }

  return client.sendClientTelemetry(
    requestId,
    payload,
  );
}
