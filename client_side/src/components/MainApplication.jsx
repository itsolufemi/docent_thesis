import React, { useEffect, useRef, useState } from 'react';
import StartScreen from './StartScreen';
import MainApp from './MainApp';
import { connectToServer, makeServerRequest } from './utils/server_functions';
import { AudioStreamClient } from '../api/audioStreamClient';
import {
  requestConversationIntroduction,
} from '../api/conversationApi';
import { synthesiseSpeech } from '../api/ttsApi';
import { TtsStreamClient } from '../api/ttsStreamClient';
import { TurnStreamClient } from '../api/turnStreamClient';
import { calculateRemainingSilenceMs } from '../audio/vadMath';
import {
  extractSpeakableSentences,
} from '../audio/sentenceBuffer';
import {
  sendCompletedVoiceTelemetry,
} from '../audio/voiceTelemetry';

const FORCED_FINALISATION_SILENCE_MS = 3000;
const INITIAL_VAD_SILENCE_MS = 500;
const BARGE_IN_CONFIRMATION_MS = 200;
const ASSISTANT_DUCK_GAIN = 0.3;
const ASSISTANT_NORMAL_GAIN = 1.0;
const DUCK_RAMP_SECONDS = 0.08;
const RESTORE_RAMP_SECONDS = 0.12;
const MIN_PROGRESSIVE_TTS_CHARACTERS = 24;

function shouldSpeakSentence(
  sentence,
) {
  const trimmed = sentence.trim();

  if (
    trimmed.length >=
    MIN_PROGRESSIVE_TTS_CHARACTERS
  ) {
    return true;
  }

  return [
    'yes.',
    'no.',
    'certainly.',
    'of course.',
  ].includes(
    trimmed.toLowerCase(),
  );
}

function appendTranscriptSegment(
  existingTranscript,
  newSegment,
) {
  const existing = existingTranscript.trim();
  const incoming = newSegment.trim();

  if (!incoming) {
    return existing;
  }

  if (!existing) {
    return incoming;
  }

  return `${existing} ${incoming}`;
}

function elapsedSeconds(
  startedAt,
  completedAt,
) {
  if (
    startedAt == null ||
    completedAt == null
  ) {
    return null;
  }

  return Number(
    (
      (
        completedAt
        - startedAt
      ) / 1000
    ).toFixed(4),
  );
}

export default function MainApplication() {
  const [loading, setLoading] = useState(true);
  const [started, setStarted] = useState(false);
  const [recording, setRecording] = useState(false);
  const [panel, setPanel] = useState('text');
  const [tourItinerary, setTourItinerary] = useState('');
  const [testUtterance, setTestUtterance] = useState('');
  const [turnDecision, setTurnDecision] = useState('');
  const [turnRequestPending, setTurnRequestPending] = useState(false);
  const [turnRequestError, setTurnRequestError] = useState('');
  const [latestTurnResult, setLatestTurnResult] = useState(null);
  const [
    streamedAssistantResponse,
    setStreamedAssistantResponse,
  ] = useState(null);
  const [audioStreamStatus, setAudioStreamStatus] = useState('disconnected');
  const [audioStreamSummary, setAudioStreamSummary] = useState(null);
  const [audioStreamError, setAudioStreamError] = useState('');
  const [audioTranscript, setAudioTranscript] = useState('');
  const [
    latestSmartTurnResult,
    setLatestSmartTurnResult,
  ] = useState(null);
  const [
    accumulatedSpokenTranscript,
    setAccumulatedSpokenTranscript,
  ] = useState('');
  const [
    assistantAudioStatus,
    setAssistantAudioStatus,
  ] = useState('idle');
  const [
    assistantAudioError,
    setAssistantAudioError,
  ] = useState('');
  const [
    latestTtsMetadata,
    setLatestTtsMetadata,
  ] = useState(null);

  const recordingRef = useRef(null);
  const listenAudioContextRef = useRef(null);
  const listenWorkletNodeRef = useRef(null);
  const listenSourceRef = useRef(null);
  const accumulatedAudioRef = useRef([]);
  const streamRef = useRef(null);

  const audioQueue = useRef([]);
  const currentAudio = useRef(null);
  const isPlaying = useRef(false);
  const speakAudioContextRef = useRef(null);
  const ttsAbortControllerRef = useRef(null);
  const ttsPlayerNodeRef = useRef(null);
  const ttsStreamClientRef = useRef(null);
  const activeTtsStreamIdRef = useRef(null);
  const assistantGainNodeRef = useRef(null);
  const duckingTimerRef = useRef(null);
  const assistantIsDuckedRef = useRef(false);
  const assistantAudioStatusRef = useRef('idle');
  const audioStreamClientRef = useRef(null);
  const turnStreamClientRef = useRef(null);
  const turnStreamConnectionPromiseRef =
    useRef(null);
  const pendingTurnRequestsRef =
    useRef(new Map());
  const streamedResponsesRef =
    useRef(new Map());
  const textDisplayReleasedRef =
    useRef(false);
  const textDisplayRequestIdRef =
    useRef(null);
  const responseSentenceBuffersRef =
    useRef(new Map());
  const spokenResponseTextRef =
    useRef(new Map());
  const progressiveTtsQueuesRef =
    useRef(new Map());
  const activeProgressiveResponseRef =
    useRef(null);
  const cancelledProgressiveResponsesRef =
    useRef(new Set());
  const activeTtsClientsByRequestRef =
    useRef(new Map());
  const spokenTurnTranscriptRef = useRef('');
  const processTurnTranscriptRef = useRef(null);
  const turnRequestPendingRef = useRef(false);
  const pendingAudioSegmentIdsRef = useRef([]);
  const completedAudioSegmentsRef = useRef(new Map());
  const processingAudioSegmentsRef = useRef(false);
  const processCompletedAudioSegmentsRef = useRef(null);
  const vadSpeechActiveRef = useRef(false);
  const vadSpeechEndedAtRef = useRef(null);
  const awaitingSpeechContinuationRef = useRef(false);
  const silenceReevaluationTimerRef = useRef(null);
  const smartTurnEnabledRef = useRef(false);
  const smartTurnCandidateIdRef = useRef(0);
  const smartTurnForcedTimerRef = useRef(null);
  const responseTimingsRef = useRef(new Map());

  const ensurePersistentTtsClient = () => {
    let client = ttsStreamClientRef.current;

    if (client) {
      return client;
    }

    client = new TtsStreamClient({
      onReady: (metadata) => {
        console.log(
          'Persistent TTS ready:',
          metadata,
        );
      },
      onClose: () => {
        if (
          ttsStreamClientRef.current === client
        ) {
          ttsStreamClientRef.current = null;
        }
      },
    });
    ttsStreamClientRef.current = client;
    return client;
  };

  const releaseStreamedTextDisplay = (
    requestId,
    fallbackText = '',
  ) => {
    if (
      !requestId ||
      textDisplayRequestIdRef.current !==
        requestId ||
      isProgressiveResponseCancelled(
        requestId,
      )
    ) {
      return;
    }

    textDisplayReleasedRef.current = true;

    const currentText =
      streamedResponsesRef.current.get(
        requestId,
      ) || fallbackText;

    setStreamedAssistantResponse(
      currentText,
    );
  };

  const setAssistantGain = (
    targetGain,
    rampSeconds,
  ) => {
    const audioContext =
      speakAudioContextRef.current;
    const gainNode =
      assistantGainNodeRef.current;

    if (
      !audioContext ||
      !gainNode ||
      audioContext.state === 'closed'
    ) {
      return;
    }

    const now = audioContext.currentTime;
    const gain = gainNode.gain;

    gain.cancelScheduledValues(now);
    gain.setValueAtTime(
      gain.value,
      now,
    );
    gain.linearRampToValueAtTime(
      targetGain,
      now + rampSeconds,
    );
  };

  const duckAssistantAudio = () => {
    if (assistantIsDuckedRef.current) {
      return;
    }

    assistantIsDuckedRef.current = true;
    setAssistantGain(
      ASSISTANT_DUCK_GAIN,
      DUCK_RAMP_SECONDS,
    );
  };

  const restoreAssistantAudio = () => {
    if (!assistantIsDuckedRef.current) {
      return;
    }

    assistantIsDuckedRef.current = false;
    setAssistantGain(
      ASSISTANT_NORMAL_GAIN,
      RESTORE_RAMP_SECONDS,
    );
  };

  const clearDuckingTimer = () => {
    if (!duckingTimerRef.current) {
      return;
    }

    window.clearTimeout(
      duckingTimerRef.current,
    );
    duckingTimerRef.current = null;
  };

  const clearSilenceReevaluationTimer = () => {
    if (silenceReevaluationTimerRef.current) {
      window.clearTimeout(
        silenceReevaluationTimerRef.current,
      );

      silenceReevaluationTimerRef.current = null;
    }
  };

  const clearSmartTurnForcedTimer = () => {
    if (!smartTurnForcedTimerRef.current) {
      return;
    }

    window.clearTimeout(
      smartTurnForcedTimerRef.current,
    );
    smartTurnForcedTimerRef.current = null;
  };

  const handleVadSpeechStart = () => {
    smartTurnCandidateIdRef.current += 1;
    vadSpeechActiveRef.current = true;
    vadSpeechEndedAtRef.current = null;
    awaitingSpeechContinuationRef.current = false;
    clearSilenceReevaluationTimer();
    clearSmartTurnForcedTimer();
    clearDuckingTimer();

    const assistantIsActive =
      assistantAudioStatusRef.current ===
        'synthesising' ||
      assistantAudioStatusRef.current ===
        'playing';

    if (!assistantIsActive) {
      return;
    }

    duckingTimerRef.current =
      window.setTimeout(() => {
        duckingTimerRef.current = null;

        if (!vadSpeechActiveRef.current) {
          return;
        }

        const assistantStillActive =
          assistantAudioStatusRef.current ===
            'synthesising' ||
          assistantAudioStatusRef.current ===
            'playing';

        if (assistantStillActive) {
          duckAssistantAudio();
        }
      }, BARGE_IN_CONFIRMATION_MS);
  };

  const handleVadSpeechEnd = (
    silenceDurationMs = INITIAL_VAD_SILENCE_MS,
  ) => {
    vadSpeechActiveRef.current = false;
    vadSpeechEndedAtRef.current =
      performance.now() -
      Math.max(0, silenceDurationMs);
    clearDuckingTimer();
  };

  const scheduleSmartTurnForcedFinalisation = ({
    candidateId,
  }) => {
    clearSmartTurnForcedTimer();

    const remainingSilenceMs =
      calculateRemainingSilenceMs({
        speechEndedAtMs:
          vadSpeechEndedAtRef.current,
        nowMs: performance.now(),
        initialSilenceMs:
          INITIAL_VAD_SILENCE_MS,
        forcedFinalisationSilenceMs:
          FORCED_FINALISATION_SILENCE_MS,
      });

    smartTurnForcedTimerRef.current =
      window.setTimeout(() => {
        smartTurnForcedTimerRef.current = null;

        if (
          vadSpeechActiveRef.current ||
          candidateId !==
            smartTurnCandidateIdRef.current
        ) {
          return;
        }

        finaliseAudioSegment(
          FORCED_FINALISATION_SILENCE_MS,
          {
            candidateId,
            forcedFinalisation: true,
          },
        );
      }, remainingSilenceMs);
  };

  const scheduleSilenceReevaluation = (
    transcript,
  ) => {
    clearSilenceReevaluationTimer();

    const speechEndedAt =
      vadSpeechEndedAtRef.current;

    const remainingSilenceMs =
      calculateRemainingSilenceMs({
        speechEndedAtMs: speechEndedAt,
        nowMs: performance.now(),
        initialSilenceMs:
          INITIAL_VAD_SILENCE_MS,
        forcedFinalisationSilenceMs:
          FORCED_FINALISATION_SILENCE_MS,
      });

    silenceReevaluationTimerRef.current =
      window.setTimeout(async () => {
        silenceReevaluationTimerRef.current = null;

        if (
          vadSpeechActiveRef.current ||
          !awaitingSpeechContinuationRef.current ||
          !recordingRef.current
        ) {
          return;
        }

        if (turnRequestPendingRef.current) {
          scheduleSilenceReevaluation(transcript);
          return;
        }

        const result =
          await processTurnTranscriptRef.current?.(
            transcript,
            {
              silenceDurationMs:
                FORCED_FINALISATION_SILENCE_MS,
            },
          );

        if (result?.turn.should_finalise_turn) {
          clearSilenceReevaluationTimer();
          awaitingSpeechContinuationRef.current =
            false;
          spokenTurnTranscriptRef.current = '';
          setAccumulatedSpokenTranscript('');
        }
      }, remainingSilenceMs);
  };

  useEffect(() => {
    if (!recording) {
      vadSpeechActiveRef.current = false;
      vadSpeechEndedAtRef.current = null;
      awaitingSpeechContinuationRef.current =
        false;
      clearSilenceReevaluationTimer();
      clearSmartTurnForcedTimer();
      clearDuckingTimer();
      restoreAssistantAudio();
    }
  }, [recording]);

  useEffect(() => {
    assistantAudioStatusRef.current =
      assistantAudioStatus;
  }, [assistantAudioStatus]);

  useEffect(() => {
    const ttsClient = ensurePersistentTtsClient();

    void ttsClient.connect().catch((error) => {
      console.error(
        'Could not connect persistent TTS:',
        error,
      );
      setAssistantAudioError(error.message);
    });
  }, []);

  useEffect(() => {
    return () => {
      clearSilenceReevaluationTimer();
      clearSmartTurnForcedTimer();
      clearDuckingTimer();

      ttsAbortControllerRef.current?.abort();

      turnStreamClientRef.current?.close();
      turnStreamClientRef.current = null;
      turnStreamConnectionPromiseRef.current =
        null;

      for (
        const pendingRequest
        of pendingTurnRequestsRef.current.values()
      ) {
        pendingRequest.reject(
          new Error('Turn stream closed.'),
        );
      }

      pendingTurnRequestsRef.current.clear();
      streamedResponsesRef.current.clear();
      textDisplayReleasedRef.current = false;
      textDisplayRequestIdRef.current = null;
      responseSentenceBuffersRef.current.clear();
      spokenResponseTextRef.current.clear();
      progressiveTtsQueuesRef.current.clear();
      responseTimingsRef.current.clear();
      activeProgressiveResponseRef.current =
        null;
      cancelledProgressiveResponsesRef.current
        .clear();

      for (
        const clients
        of activeTtsClientsByRequestRef
          .current
          .values()
      ) {
        for (const client of [...clients]) {
          client.close();
        }
      }

      activeTtsClientsByRequestRef.current.clear();

      if (currentAudio.current) {
        currentAudio.current.onended = null;

        try {
          currentAudio.current.stop();
        } catch {
          // The source may already have ended.
        }

        currentAudio.current = null;
      }

      ttsStreamClientRef.current?.close();
      ttsStreamClientRef.current = null;

      if (ttsPlayerNodeRef.current) {
        ttsPlayerNodeRef.current.port.onmessage =
          null;
        ttsPlayerNodeRef.current.disconnect();
        ttsPlayerNodeRef.current = null;
      }

      if (assistantGainNodeRef.current) {
        assistantGainNodeRef.current.disconnect();
        assistantGainNodeRef.current = null;
      }

      const audioContext =
        speakAudioContextRef.current;

      if (
        audioContext &&
        audioContext.state !== 'closed'
      ) {
        audioContext.close().catch((error) => {
          console.warn(
            'Could not close assistant audio context:',
            error,
          );
        });
      }
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadingFallbackTimeout = window.setTimeout(() => {
      if (!cancelled) {
        setLoading(false);
      }
    }, 1500);

    async function connect() {
      try {
        await connectToServer({
          panel,
          handleSetPanel: setPanel,
          handleSetTour_itinerary: setTourItinerary,
          setAudioQueue: (queue) => {
            audioQueue.current = queue;
          },
          audioQueue,
          isPlaying,
          setIsPlaying: (status) => {
            isPlaying.current = status;
          },
          currentAudio,
          setCurrentAudio: (audio) => {
            currentAudio.current = audio;
          },
        });

      } catch (error) {
        console.error('Error connecting to the server:', error);
      } finally {
        window.clearTimeout(loadingFallbackTimeout);

        if (!cancelled) {
          // Keep the FastAPI text path available when the legacy
          // WebSocket/audio server is not running.
          setLoading(false);
        }
      }
    }

    connect();

    return () => {
      cancelled = true;
      window.clearTimeout(loadingFallbackTimeout);
    };
  }, []);

  useEffect(() => {
    const audioClient = new AudioStreamClient({
      onOpen: () => {
        setAudioStreamStatus('connected');
        setAudioStreamError('');
      },
      onMessage: (message) => {
        console.log('Audio stream message:', message);

        switch (message.type) {
          case 'audio_segment_started':
            smartTurnEnabledRef.current = Boolean(
              message.payload?.smart_turn_enabled,
            );
            setAudioStreamStatus('streaming');
            setAudioStreamSummary(null);
            setAudioTranscript('');
            setLatestSmartTurnResult(null);
            setAudioStreamError('');
            setTurnRequestError('');
            break;
          case 'audio_stream_complete':
            setAudioStreamStatus('connected');
            setAudioStreamSummary(message.payload);
            break;
          case 'smart_turn_started':
            setAudioStreamStatus('evaluating turn');
            break;
          case 'smart_turn_result': {
            const candidateId =
              message.payload?.candidate_id;

            setLatestSmartTurnResult(
              message.payload,
            );

            if (
              message.payload?.stale ||
              candidateId !==
                smartTurnCandidateIdRef.current
            ) {
              break;
            }

            if (
              message.payload?.turn_complete &&
              !vadSpeechActiveRef.current
            ) {
              clearSmartTurnForcedTimer();
              finaliseAudioSegment(
                message.payload
                  .silence_duration_ms ??
                  INITIAL_VAD_SILENCE_MS,
                {
                  candidateId,
                  forcedFinalisation: false,
                },
              );
            } else if (
              !message.payload?.turn_complete
            ) {
              setAudioStreamStatus('listening');
            }

            break;
          }
          case 'awaiting_speech_continuation':
            if (
              message.payload?.candidate_id ===
              smartTurnCandidateIdRef.current
            ) {
              setAudioStreamStatus('listening');
            }
            break;
          case 'transcription_started':
            clearSmartTurnForcedTimer();
            setAudioStreamStatus('transcribing');
            break;
          case 'audio_transcription': {
            const segmentId =
              message.payload?.segment_id;

            if (!segmentId) {
              setAudioStreamError(
                'Transcription result had no segment ID.',
              );
              break;
            }

            completedAudioSegmentsRef.current.set(
              segmentId,
              message.payload,
            );

            processCompletedAudioSegmentsRef.current?.();

            break;
          }
          case 'audio_segment_cancelled': {
            const segmentId =
              message.payload?.segment_id;

            pendingAudioSegmentIdsRef.current =
              pendingAudioSegmentIdsRef.current.filter(
                (pendingId) => pendingId !== segmentId,
              );
            completedAudioSegmentsRef.current.delete(
              segmentId,
            );
            clearSilenceReevaluationTimer();
            clearSmartTurnForcedTimer();
            awaitingSpeechContinuationRef.current =
              false;
            setAudioStreamStatus('connected');
            processCompletedAudioSegmentsRef.current?.();
            break;
          }
          case 'audio_error': {
            const segmentId =
              message.payload?.segment_id;

            if (
              segmentId &&
              message.payload?.candidate_id == null
            ) {
              pendingAudioSegmentIdsRef.current =
                pendingAudioSegmentIdsRef.current.filter(
                  (pendingId) => pendingId !== segmentId,
                );
              completedAudioSegmentsRef.current.delete(
                segmentId,
              );
              clearSilenceReevaluationTimer();
              clearSmartTurnForcedTimer();
              awaitingSpeechContinuationRef.current =
                false;
              processCompletedAudioSegmentsRef.current?.();
            }

            setAudioStreamStatus('connected');
            setAudioStreamError(
              message.payload?.detail ??
              'Unknown audio-stream error.',
            );
            break;
          }
          default:
            console.warn(
              'Unknown audio stream event:',
              message,
            );
        }
      },
      onError: () => {
        setAudioStreamStatus('error');
        setAudioStreamError(
          'Could not connect to the FastAPI audio stream.',
        );
      },
      onClose: () => {
        setAudioStreamStatus('disconnected');
      },
    });

    audioStreamClientRef.current = audioClient;

    audioClient.connect().catch((error) => {
      console.error(
        'Audio WebSocket connection failed:',
        error,
      );
    });

    return () => {
      audioClient.close();
      audioStreamClientRef.current = null;
    };
  }, []);

  const handleStartClick = async () => {
    setStarted(true);
    setPanel('text');

    if (!speakAudioContextRef.current) {
      speakAudioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 24000,
      });
    }

    speakAudioContextRef.current.resume();

    try {
      const introduction =
        await requestConversationIntroduction();

      if (introduction.text) {
        setStreamedAssistantResponse(
          introduction.text,
        );
        void streamAssistantResponse(
          introduction.text,
        );
      }
    } catch (error) {
      console.error(
        'Could not generate the conversation introduction:',
        error,
      );
      setAssistantAudioError(
        error instanceof Error
          ? error.message
          : 'The introduction request failed.',
      );
    }
  };

  const sendChunkToServer = (chunk) => {
    const sent = audioStreamClientRef.current?.sendChunk(chunk);

    if (!sent) {
      console.warn(
        'PCM chunk was not sent because the audio ' +
        'WebSocket is not open.',
      );
    }
  };

  const startAudioSegment = async () => {
    const audioClient = audioStreamClientRef.current;

    if (!audioClient) {
      throw new Error('Audio stream client is unavailable.');
    }

    if (
      !audioClient.socket ||
      audioClient.socket.readyState !== WebSocket.OPEN
    ) {
      await audioClient.connect();
    }

    setAudioStreamError('');

    if (audioClient.currentSegmentId) {
      audioClient.notifySpeechResumed({
        candidateId:
          smartTurnCandidateIdRef.current,
      });
      setAudioStreamStatus('streaming');
      return audioClient.currentSegmentId;
    }

    const segmentId = audioClient.startSegment({
      sampleRate: 16000,
      channels: 1,
    });

    pendingAudioSegmentIdsRef.current.push(
      segmentId,
    );

    return segmentId;
  };

  const finaliseAudioSegment = (
    silenceDurationMs =
      INITIAL_VAD_SILENCE_MS,
    {
      candidateId = null,
      forcedFinalisation = false,
    } = {},
  ) => {
    clearSmartTurnForcedTimer();

    try {
      audioStreamClientRef.current?.finaliseSegment({
        silenceDurationMs,
        candidateId,
        forcedFinalisation,
      });
    } catch (error) {
      console.error(
        'Could not finalise audio segment:',
        error,
      );
    }
  };

  const evaluateAudioSegmentCandidate = (
    silenceDurationMs =
      INITIAL_VAD_SILENCE_MS,
  ) => {
    if (!smartTurnEnabledRef.current) {
      finaliseAudioSegment(silenceDurationMs);
      return;
    }

    smartTurnCandidateIdRef.current += 1;
    const candidateId =
      smartTurnCandidateIdRef.current;

    try {
      audioStreamClientRef.current
        ?.evaluateCandidate({
          candidateId,
          silenceDurationMs,
        });
      setAudioStreamStatus('evaluating turn');
      scheduleSmartTurnForcedFinalisation({
        candidateId,
      });
    } catch (error) {
      console.error(
        'Could not evaluate Smart Turn candidate:',
        error,
      );
    }
  };

  const cancelAudioSegment = () => {
    smartTurnCandidateIdRef.current += 1;
    clearSilenceReevaluationTimer();
    clearSmartTurnForcedTimer();
    awaitingSpeechContinuationRef.current = false;

    try {
      audioStreamClientRef.current?.cancelSegment();
    } catch (error) {
      console.error(
        'Could not cancel audio segment:',
        error,
      );
    }
  };

  const notifyPlaybackComplete = () => {
    makeServerRequest('playback_complete', null);
  };

  const stopAssistantAudio = () => {
    clearDuckingTimer();

    ttsAbortControllerRef.current?.abort();
    ttsAbortControllerRef.current = null;

    ttsStreamClientRef.current?.cancel(
      activeTtsStreamIdRef.current,
    );

    activeTtsStreamIdRef.current = null;

    ttsPlayerNodeRef.current?.port.postMessage({
      type: 'flush',
    });

    if (currentAudio.current) {
      const source = currentAudio.current;

      currentAudio.current = null;
      source.onended = null;

      try {
        source.stop();
      } catch {
        // The source may already have ended.
      }
    }

    isPlaying.current = false;
    restoreAssistantAudio();
    setAssistantAudioStatus('idle');
  };

  const isProgressiveResponseCancelled = (
    requestId,
  ) =>
    cancelledProgressiveResponsesRef.current.has(
      requestId,
    );

  const removeTtsClientForRequest = (
    requestId,
    client,
  ) => {
    if (!requestId) {
      return;
    }

    const clients =
      activeTtsClientsByRequestRef.current.get(
        requestId,
      );

    if (!clients) {
      return;
    }

    clients.delete(client);

    if (clients.size === 0) {
      activeTtsClientsByRequestRef.current.delete(
        requestId,
      );
    }
  };

  const cancelProgressiveTtsResponse = (
    requestId,
    {
      cancelServerTurn = true,
    } = {},
  ) => {
    if (!requestId) {
      return;
    }

    cancelledProgressiveResponsesRef.current.add(
      requestId,
    );

    if (cancelServerTurn) {
      turnStreamClientRef.current?.cancelTurn(
        requestId,
      );
    }

    turnStreamClientRef.current
      ?.sendClientTelemetry(
        requestId,
        {
          cancelled: true,
          partialTiming:
            responseTimingsRef.current.get(
              requestId,
            ) ?? null,
        },
      );

    ttsStreamClientRef.current?.cancel(
      activeTtsStreamIdRef.current,
    );

    activeTtsClientsByRequestRef.current.delete(
      requestId,
    );
    responseSentenceBuffersRef.current.delete(
      requestId,
    );
    progressiveTtsQueuesRef.current.delete(
      requestId,
    );
    spokenResponseTextRef.current.delete(
      requestId,
    );
    responseTimingsRef.current.delete(
      requestId,
    );

    const cancellingActiveResponse = (
      activeProgressiveResponseRef.current
        ?.requestId === requestId
    );

    if (cancellingActiveResponse) {
      activeProgressiveResponseRef.current
        .cancelled = true;
      activeProgressiveResponseRef.current =
        null;
    }

    if (
      textDisplayRequestIdRef.current ===
      requestId
    ) {
      textDisplayReleasedRef.current = false;
      textDisplayRequestIdRef.current = null;
    }

    if (cancellingActiveResponse) {
      stopAssistantAudio();
    }
  };

  const stopCurrentAssistantResponse =
  () => {
    const activeResponse =
      activeProgressiveResponseRef
        .current;

    if (!activeResponse?.requestId) {
      stopAssistantAudio();
      return;
    }

    cancelProgressiveTtsResponse(
      activeResponse.requestId,
    );
  };

  const rejectPendingTurnRequests = (
    error,
  ) => {
    for (
      const pendingRequest
      of pendingTurnRequestsRef.current.values()
    ) {
      pendingRequest.reject(error);
    }

    pendingTurnRequestsRef.current.clear();
  };

  const ensureTurnStream = async () => {
    const existingClient =
      turnStreamClientRef.current;

    if (
      existingClient?.socket?.readyState ===
      WebSocket.OPEN
    ) {
      return existingClient;
    }

    if (
      existingClient &&
      turnStreamConnectionPromiseRef.current
    ) {
      await turnStreamConnectionPromiseRef.current;
      return existingClient;
    }

    const client = new TurnStreamClient({
      onReady: (payload) => {
        console.log(
          'Turn stream ready:',
          payload,
        );
      },

      onTurnEvaluated: ({
        requestId,
        payload,
      }) => {
        console.log(
          'Turn evaluated:',
          payload,
        );

        const pendingRequest =
          pendingTurnRequestsRef.current.get(
            requestId,
          );

        if (!pendingRequest) {
          return;
        }

        pendingRequest.turn = payload;

        if (!payload.should_finalise_turn) {
          pendingTurnRequestsRef.current.delete(
            requestId,
          );

          pendingRequest.resolve({
            turn: payload,
            utterance_route: null,
            query: null,
          });
        }
      },

      onUtteranceClassified: ({
        requestId,
        payload,
      }) => {
        console.log(
          'Utterance classified:',
          payload,
        );

        const pendingRequest =
          pendingTurnRequestsRef.current.get(
            requestId,
          );

        if (pendingRequest) {
          pendingRequest.route = payload;
        }

        const floorIntent =
          payload.floor_intent;

        if (floorIntent === 'take_floor') {
          const activeResponse =
            activeProgressiveResponseRef.current;

          if (activeResponse) {
            activeResponse.cancelled = true;

            cancelProgressiveTtsResponse(
              activeResponse.requestId,
            );
          } else {
            stopAssistantAudio();
          }

          return;
        }

        if (
          floorIntent === 'backchannel' ||
          floorIntent === 'none'
        ) {
          restoreAssistantAudio();
        }
      },

      onSelfRouting: ({
        requestId,
        payload,
      }) => {
        console.log(
          'Model self-routing:',
          payload,
        );

        const pendingRequest =
          pendingTurnRequestsRef.current.get(
            requestId,
          );

        if (pendingRequest) {
          pendingRequest.selfRouting =
            payload.assessment ?? null;
        }
      },

      onQueryStarted: ({
        requestId,
        payload,
      }) => {
        console.log(
          'Turn query started:',
          payload,
        );

        if (
          !isProgressiveResponseCancelled(
            requestId,
          )
        ) {
          activeProgressiveResponseRef.current = {
            requestId,
            llmComplete: false,
            synthesisComplete: false,
            playbackComplete: true,
            cancelled: false,
          };

          responseTimingsRef.current.set(
            requestId,
            {
              queryStartedAt: performance.now(),
              firstDeltaAt: null,
              firstSentenceQueuedAt: null,
              firstTtsRequestAt: null,
              firstTtsAudioAt: null,
              firstPlaybackAt: null,

              serverFirstDeltaSeconds: null,

              firstDeltaPayload: null,
              firstAudioPayload: null,
              playbackPayload: null,

              ttsGenerations: [],
              bufferUnderrunCount: 0,

              queryCompletePayload: null,
            },
          );
        }

        const pendingRequest =
          pendingTurnRequestsRef.current.get(
            requestId,
          );

        if (
          pendingRequest &&
          !pendingRequest.released
        ) {
          pendingRequest.released = true;
          pendingRequest.resolve({
            turn: pendingRequest.turn,
            utterance_route:
              pendingRequest.route,
            query: null,
            query_pending: true,
          });
        }

        setTurnRequestPending(false);
      },

      onResponseStarted: ({
        requestId,
      }) => {
        if (
          isProgressiveResponseCancelled(
            requestId,
          )
        ) {
          return;
        }

        textDisplayRequestIdRef.current =
          requestId;
        textDisplayReleasedRef.current =
          false;

        stopAssistantAudio();
        streamedResponsesRef.current.set(
          requestId,
          '',
        );
        responseSentenceBuffersRef.current.set(
          requestId,
          '',
        );
        spokenResponseTextRef.current.set(
          requestId,
          '',
        );
        progressiveTtsQueuesRef.current.set(
          requestId,
          Promise.resolve(),
        );
        activeProgressiveResponseRef.current = {
          requestId,
          llmComplete: false,
          synthesisComplete: false,
          playbackComplete: true,
          cancelled: false,
        };
        setStreamedAssistantResponse('');
      },

      onResponseFirstDelta: ({
        requestId,
        payload,
      }) => {
        if (
          isProgressiveResponseCancelled(
            requestId,
          )
        ) {
          return;
        }

        const timing =
          responseTimingsRef.current.get(
            requestId,
          );

        timing.firstDeltaPayload = payload;

        if (
          timing &&
          timing.firstDeltaAt === null
        ) {
          timing.firstDeltaAt =
            performance.now();

          timing.serverFirstDeltaSeconds =
            payload.seconds ?? null;
        }

        console.log(
          'LLM first delta timing:',
          payload,
        );
      },

      onResponseDelta: ({
        requestId,
        payload,
      }) => {
        if (
          isProgressiveResponseCancelled(
            requestId,
          )
        ) {
          return;
        }

        const delta = payload.text ?? '';
        const existingText =
          streamedResponsesRef.current.get(
            requestId,
          ) ?? '';
        const updatedText =
          `${existingText}${delta}`;

        streamedResponsesRef.current.set(
          requestId,
          updatedText,
        );

        if (
          textDisplayRequestIdRef.current ===
            requestId &&
          textDisplayReleasedRef.current
        ) {
          setStreamedAssistantResponse(
            updatedText,
          );
        }

        const existingBuffer =
          responseSentenceBuffersRef
            .current
            .get(requestId) ?? '';
        const updatedBuffer =
          `${existingBuffer}${delta}`;
        const {
          sentences,
          remainder,
        } = extractSpeakableSentences(
          updatedBuffer,
        );
        let retainedText = '';

        for (const sentence of sentences) {
          const candidateSentence =
            `${retainedText} ${sentence}`
              .trim();

          if (
            shouldSpeakSentence(
              candidateSentence,
            )
          ) {
            enqueueProgressiveTtsSentence(
              requestId,
              candidateSentence,
            );
            retainedText = '';
          } else {
            retainedText =
              candidateSentence;
          }
        }

        responseSentenceBuffersRef.current.set(
          requestId,
          `${retainedText} ${remainder}`
            .trimStart(),
        );
      },

      onToolCallStarted: ({
        requestId,
        payload,
      }) => {
        if (
          isProgressiveResponseCancelled(
            requestId,
          )
        ) {
          return;
        }

        console.log(
          'Tool call started:',
          payload,
        );
      },

      onToolCallComplete: ({
        requestId,
        payload,
      }) => {
        if (
          isProgressiveResponseCancelled(
            requestId,
          )
        ) {
          return;
        }

        console.log(
          'Tool call complete:',
          payload,
        );
      },

      onResponseComplete: ({
        requestId,
        payload,
      }) => {
        if (
          isProgressiveResponseCancelled(
            requestId,
          )
        ) {
          return;
        }

        const streamedText =
          streamedResponsesRef.current.get(
            requestId,
          ) ?? '';
        const completedText =
          payload.response ??
          streamedText;

        streamedResponsesRef.current.set(
          requestId,
          completedText,
        );
        releaseStreamedTextDisplay(
          requestId,
          completedText,
        );

        const remainder =
          responseSentenceBuffersRef.current
            .get(requestId)
            ?.trim() ?? '';

        if (remainder) {
          enqueueProgressiveTtsSentence(
            requestId,
            remainder,
          );
          responseSentenceBuffersRef.current.set(
            requestId,
            '',
          );
        }

        const activeResponse =
          activeProgressiveResponseRef.current;

        if (
          activeResponse?.requestId ===
          requestId
        ) {
          activeResponse.llmComplete = true;
        }
      },

      onTurnCancelled: ({
        requestId,
      }) => {
        cancelledProgressiveResponsesRef
          .current
          .add(requestId);

        const pendingRequest =
          pendingTurnRequestsRef.current.get(
            requestId,
          );

        if (
          pendingRequest &&
          !pendingRequest.released
        ) {
          pendingRequest.released = true;
          pendingRequest.resolve({
            turn: pendingRequest.turn,
            utterance_route:
              pendingRequest.route,
            query: null,
            cancelled: true,
          });
        }

        pendingTurnRequestsRef.current.delete(
          requestId,
        );

        cancelProgressiveTtsResponse(
          requestId,
          {
            cancelServerTurn: false,
          },
        );
      },

      onQueryComplete: ({
        requestId,
        payload,
      }) => {
        if (
          isProgressiveResponseCancelled(
            requestId,
          )
        ) {
          pendingTurnRequestsRef.current.delete(
            requestId,
          );
          return;
        }

        console.log(
          'Turn query complete:',
          payload,
        );
        setTurnRequestPending(false);

        const pendingRequest =
          pendingTurnRequestsRef.current.get(
            requestId,
          );
        const streamedText =
          streamedResponsesRef.current.get(
            requestId,
          ) ?? '';
        const spokenText =
          spokenResponseTextRef.current.get(
            requestId,
          ) ?? '';

        console.log({
          streamedText,
          finalText: payload.response,
          equal:
            streamedText.trim() ===
            (payload.response ?? '').trim(),
        });

        pendingTurnRequestsRef.current.delete(
          requestId,
        );
        releaseStreamedTextDisplay(
          requestId,
          payload.response ?? streamedText,
        );

        if (
          !spokenText.trim() &&
          payload.response?.trim()
        ) {
          enqueueProgressiveTtsSentence(
            requestId,
            payload.response,
          );
        }

        const timing =
          responseTimingsRef.current.get(
            requestId,
          );

        if (timing) {
          timing.queryCompletePayload =
            payload;
        }

        finishProgressiveTtsQueue(
          requestId,
        );

        if (pendingRequest) {
          const completedResult = {
            turn: pendingRequest.turn,
            utterance_route:
              pendingRequest.route,
            query: payload,
          };

          setLatestTurnResult(
            completedResult,
          );
          setTurnDecision(
            pendingRequest.turn?.decision ??
            '',
          );
          pendingRequest.resolve(
            completedResult,
          );
        }
      },

      onError: (
        error,
        requestId,
      ) => {
        setTurnRequestPending(false);
        releaseStreamedTextDisplay(
          requestId,
        );

        if (requestId) {
          responseTimingsRef.current.delete(
            requestId,
          );
        }

        const pendingRequest =
          pendingTurnRequestsRef.current.get(
            requestId,
          );

        if (pendingRequest) {
          pendingTurnRequestsRef.current.delete(
            requestId,
          );
          pendingRequest.reject(error);
        } else {
          rejectPendingTurnRequests(error);
          setTurnRequestError(
            error.message,
          );
        }
      },

      onClose: () => {
        if (
          turnStreamClientRef.current ===
          client
        ) {
          turnStreamClientRef.current =
            null;
        }

        setTurnRequestPending(false);
        rejectPendingTurnRequests(
          new Error('Turn stream closed.'),
        );
      },
    });

    turnStreamClientRef.current = client;

    const connectionPromise =
      client.connect();

    turnStreamConnectionPromiseRef.current =
      connectionPromise;

    try {
      await connectionPromise;
      return client;
    } catch (error) {
      if (
        turnStreamClientRef.current ===
        client
      ) {
        turnStreamClientRef.current =
          null;
      }

      throw error;
    } finally {
      if (
        turnStreamConnectionPromiseRef.current ===
        connectionPromise
      ) {
        turnStreamConnectionPromiseRef.current =
          null;
      }
    }
  };

  const sendStreamedTurnEvent = async ({
    partialUtterance,
    isSpeechActive,
    silenceDurationMs,
    turnCompletionConfirmed = false,
    debug = false,
  }) => {
    const client =
      await ensureTurnStream();

    return new Promise(
      (resolve, reject) => {
        const requestId =
          client.sendTurnEvent({
            partialUtterance,
            isSpeechActive,
            silenceDurationMs,
            assistantWasSpeaking:
              assistantAudioStatusRef.current ===
                'synthesising' ||
              assistantAudioStatusRef.current ===
                'playing',
            turnCompletionConfirmed,
            debug,
          });

        pendingTurnRequestsRef.current.set(
          requestId,
          {
            resolve,
            reject,
            turn: null,
            route: null,
            selfRouting: null,
            released: false,
          },
        );
      },
    );
  };

  const completeProgressiveResponseIfReady =
    () => {
      const activeResponse =
        activeProgressiveResponseRef.current;

      if (
        !activeResponse ||
        !activeResponse.llmComplete ||
        !activeResponse.synthesisComplete ||
        !activeResponse.playbackComplete
      ) {
        return false;
      }

      const completedRequestId =
        activeResponse.requestId;

      activeProgressiveResponseRef.current =
        null;

      const timing =
        responseTimingsRef.current.get(
          completedRequestId,
        );

      sendCompletedVoiceTelemetry({
        client:
          turnStreamClientRef.current,
        requestId: completedRequestId,
        timing,
      });

      responseTimingsRef.current.delete(
        completedRequestId,
      );

      isPlaying.current = false;
      activeTtsStreamIdRef.current = null;
      restoreAssistantAudio();
      setAssistantAudioStatus('idle');
      notifyPlaybackComplete();

      return true;
    };

  const ensureTtsPlayer = async () => {
    let audioContext =
      speakAudioContextRef.current;

    if (
      !audioContext ||
      audioContext.state === 'closed'
    ) {
      audioContext = new (
        window.AudioContext ||
        window.webkitAudioContext
      )({
        sampleRate: 24000,
      });

      speakAudioContextRef.current =
        audioContext;
    }

    if (
      audioContext.state === 'suspended'
    ) {
      await audioContext.resume();
    }

    if (!ttsPlayerNodeRef.current) {
      await audioContext.audioWorklet.addModule(
        '/worklets/tts-pcm-player.worklet.js',
      );

      const playerNode =
        new AudioWorkletNode(
          audioContext,
          'tts-pcm-player',
          {
            outputChannelCount: [1],
          },
        );

      let gainNode =
        assistantGainNodeRef.current;

      if (!gainNode) {
        gainNode =
          audioContext.createGain();
        gainNode.gain.value =
          assistantIsDuckedRef.current
            ? ASSISTANT_DUCK_GAIN
            : ASSISTANT_NORMAL_GAIN;
        gainNode.connect(
          audioContext.destination,
        );
        assistantGainNodeRef.current =
          gainNode;
      }

      playerNode.connect(gainNode);

      playerNode.port.onmessage = (
        event,
      ) => {
        switch (event.data?.type) {
          case 'playback_started': {
            isPlaying.current = true;

            const activeRequestId =
              activeProgressiveResponseRef.current
                ?.requestId;

            const responseTiming =
              activeRequestId
                ? responseTimingsRef.current.get(
                    activeRequestId,
                  )
                : null;

            if (
              responseTiming &&
              responseTiming.firstPlaybackAt ===
                null
            ) {
              responseTiming.firstPlaybackAt =
                performance.now();

              const playbackPayload = {
                firstAudioToPlaybackSeconds:
                  elapsedSeconds(
                    responseTiming.firstTtsAudioAt,
                    responseTiming.firstPlaybackAt,
                  ),

                queryToPlaybackSeconds:
                  elapsedSeconds(
                    responseTiming.queryStartedAt,
                    responseTiming.firstPlaybackAt,
                  ),

                bufferedSamples:
                  event.data?.bufferedSamples ??
                  null,

                bufferedMilliseconds:
                  event.data
                    ?.bufferedMilliseconds ??
                  null,
              };

              responseTiming.playbackPayload =
                playbackPayload;

              console.log(
                'Voice pipeline playback timing:',
                {
                  requestId: activeRequestId,
                  ...playbackPayload,
                },
              );
            }

            if (
              activeProgressiveResponseRef.current
            ) {
              activeProgressiveResponseRef
                .current
                .playbackComplete = false;
            }

            setAssistantAudioStatus(
              'playing',
            );
            break;
          }

          case 'playback_complete':
            if (
              activeProgressiveResponseRef.current
            ) {
              isPlaying.current = false;
              activeProgressiveResponseRef
                .current
                .playbackComplete = true;

              if (
                !completeProgressiveResponseIfReady()
              ) {
                setAssistantAudioStatus(
                  'synthesising',
                );
              }

              break;
            }

            isPlaying.current = false;
            activeTtsStreamIdRef.current =
              null;
            restoreAssistantAudio();
            setAssistantAudioStatus(
              'idle',
            );
            notifyPlaybackComplete();
            break;

          case 'playback_flushed':
            isPlaying.current = false;
            restoreAssistantAudio();

            if (
              activeProgressiveResponseRef.current
            ) {
              activeProgressiveResponseRef
                .current
                .playbackComplete = true;
              completeProgressiveResponseIfReady();
            }

            break;

          case 'buffer_underrun': {
            const requestId =
              activeProgressiveResponseRef.current
                ?.requestId;

            const timing =
              responseTimingsRef.current.get(
                requestId,
              );

            if (timing) {
              timing.bufferUnderrunCount =
                event.data?.underrunCount ?? 0;
            }

            console.log(
              'TTS playback buffer underrun:',
              {
                requestId,
                underrunCount:
                  event.data?.underrunCount,
              },
            );

          break;
          }

          default:
            break;
        }
      };

      ttsPlayerNodeRef.current =
        playerNode;
    }

    return ttsPlayerNodeRef.current;
  };

  const streamAssistantResponse = async (
    responseText,
    {
      replace = true,
      requestId = null,
    } = {},
  ) => {
    const cleanedText = responseText?.trim();

    if (!cleanedText) {
      return null;
    }

    if (
      requestId &&
      isProgressiveResponseCancelled(
        requestId,
      )
    ) {
      return null;
    }

    if (replace) {
      stopAssistantAudio();
    }

    setAssistantAudioStatus(
      'synthesising',
    );
    setAssistantAudioError('');
    setLatestTtsMetadata(null);

    try {
      const playerNode =
        await ensureTtsPlayer();

      if (
        requestId &&
        isProgressiveResponseCancelled(
          requestId,
        )
      ) {
        return null;
      }

      return await new Promise(
        (resolve, reject) => {
          let settled = false;

          const resolveOnce = (value) => {
            if (settled) {
              return;
            }

            settled = true;
            resolve(value);
          };

          const rejectOnce = (error) => {
            if (settled) {
              return;
            }

            settled = true;
            reject(error);
          };

          const ttsClient =
            ensurePersistentTtsClient();

          const synthesisPromise =
            ttsClient.synthesise({
              text: cleanedText,
              onStarted: (metadata) => {
                if (
                  requestId &&
                  isProgressiveResponseCancelled(
                    requestId,
                  )
                ) {
                  ttsClient.cancel(
                    metadata.synthesis_id,
                  );
                  return;
                }

                activeTtsStreamIdRef.current =
                  metadata.synthesis_id;
                
                const playbackSampleRate =
                  playerNode.context.sampleRate;

                console.log(
                  'TTS audio format:',
                  {
                    provider: metadata.provider,
                    sourceSampleRate:
                      metadata.sample_rate,
                    playbackSampleRate,
                    ratesMatch:
                      metadata.sample_rate ===
                      playbackSampleRate,
                  },
                );

                setLatestTtsMetadata({
                  provider:
                    metadata.provider,
                  voice:
                    metadata.voice_name,
                  language:
                    metadata.language_code,
                  sampleRate:
                    metadata.sample_rate,
                  characterCount:
                    metadata.character_count,
                  generationSeconds: 0,
                  requestId,
                });

                playerNode.port.postMessage({
                  type: 'configure',
                  prebufferMs:
                    metadata
                      .recommended_prebuffer_ms
                    ?? 120,
                });
              },



              onFirstAudio: (ttsTiming) => {
                if (!requestId) {
                  return;
                }

                const responseTiming =
                  responseTimingsRef.current.get(
                    requestId,
                  );

                if (
                  !responseTiming ||
                  responseTiming.firstTtsAudioAt
                    !== null
                ) {
                  return;
                }

                responseTiming.firstTtsAudioAt =
                  performance.now();

                responseTiming.ttsTiming =
                  ttsTiming;

                const firstAudioPayload = {
                  serverQueryToFirstDeltaSeconds:
                    responseTiming
                      .serverFirstDeltaSeconds,

                  queryToFirstDeltaSeconds:
                    elapsedSeconds(
                      responseTiming.queryStartedAt,
                      responseTiming.firstDeltaAt,
                    ),

                  firstDeltaToSentenceSeconds:
                    elapsedSeconds(
                      responseTiming.firstDeltaAt,
                      responseTiming
                        .firstSentenceQueuedAt,
                    ),

                  sentenceToTtsRequestSeconds:
                    elapsedSeconds(
                      responseTiming
                        .firstSentenceQueuedAt,
                      responseTiming
                        .firstTtsRequestAt,
                    ),

                  ttsSocketConnectSeconds:
                    ttsTiming.connectSeconds,

                  ttsConnectionReused:
                    ttsTiming.connectionReused,

                  ttsRequestToFirstAudioSeconds:
                    ttsTiming
                      .requestToFirstAudioSeconds,

                  serverTtsFirstChunkSeconds:
                    ttsTiming
                      .serverRequestToFirstChunkSeconds,

                  queryToFirstAudioSeconds:
                    elapsedSeconds(
                      responseTiming.queryStartedAt,
                      responseTiming.firstTtsAudioAt,
                    ),
                };

                responseTiming.firstAudioPayload =
                  firstAudioPayload;

                console.log(
                  'Voice pipeline first-audio timing:',
                  {
                    requestId,
                    ...firstAudioPayload,
                  },
                );
              },

              onAudioChunk: ({
                samples,
              }) => {
                if (
                  requestId &&
                  isProgressiveResponseCancelled(
                    requestId,
                  )
                ) {
                  return;
                }

                releaseStreamedTextDisplay(
                  requestId,
                );

                playerNode.port.postMessage(
                  {
                    type: 'enqueue',
                    samples,
                  },
                  [samples.buffer],
                );
              },

              onComplete: (metadata) => {
                if (
                  activeTtsStreamIdRef.current ===
                  metadata.synthesis_id
                ) {
                  activeTtsStreamIdRef.current = null;
                }
                removeTtsClientForRequest(
                  requestId,
                  ttsClient,
                );

                if (requestId) {
                  const timing =
                    responseTimingsRef.current.get(
                      requestId,
                    );

                  if (timing) {
                    timing.ttsGenerations.push({
                      synthesisId:
                        metadata.synthesis_id,
                      generationSeconds:
                        metadata
                          .generation_seconds,
                      audioDurationSeconds:
                        metadata
                          .audio_duration_seconds,
                      realtimeFactor:
                        metadata.realtime_factor,
                      chunkCount:
                        metadata.chunk_count,
                      audioBytes:
                        metadata.audio_bytes,
                      firstChunkSeconds:
                        metadata
                          .first_chunk_seconds,
                    });
                  }
                }

                setLatestTtsMetadata(
                  (current) => ({
                    ...current,
                    generationSeconds:
                      metadata.generation_seconds,
                    audioDurationSeconds:
                      metadata.audio_duration_seconds,
                    realtimeFactor:
                      metadata.realtime_factor,
                    chunkCount:
                      metadata.chunk_count,
                    audioBytes:
                      metadata.audio_bytes,
                  }),
                );

                console.log(
                  'TTS generation performance:',
                  {
                    generationSeconds:
                      metadata.generation_seconds,
                    audioDurationSeconds:
                      metadata.audio_duration_seconds,
                    realtimeFactor:
                      metadata.realtime_factor,
                  },
                );

                playerNode.port.postMessage({
                  type: 'complete',
                });

                resolveOnce(metadata);
              },

              onError: (error) => {
                removeTtsClientForRequest(
                  requestId,
                  ttsClient,
                );
                releaseStreamedTextDisplay(
                  requestId,
                );

                console.error(
                  'Streaming TTS failed:',
                  error,
                );

                playerNode.port.postMessage({
                  type: 'flush',
                });

                setAssistantAudioStatus(
                  'error',
                );
                setAssistantAudioError(
                  error.message,
                );
                rejectOnce(error);
              },

              onCancelled: (metadata) => {
                if (
                  activeTtsStreamIdRef.current ===
                  metadata.synthesis_id
                ) {
                  activeTtsStreamIdRef.current = null;
                }
                removeTtsClientForRequest(
                  requestId,
                  ttsClient,
                );
                resolveOnce(metadata);
              },
            });

          if (requestId) {
            let requestClients =
              activeTtsClientsByRequestRef
                .current
                .get(requestId);

            if (!requestClients) {
              requestClients = new Set();
              activeTtsClientsByRequestRef
                .current
                .set(
                  requestId,
                  requestClients,
                );
            }

            requestClients.add(ttsClient);
          }

          if (requestId) {
            const responseTiming =
              responseTimingsRef.current.get(
                requestId,
              );

            if (
              responseTiming &&
              responseTiming
                .firstTtsRequestAt === null
            ) {
              responseTiming.firstTtsRequestAt =
                performance.now();
            }
          }

          synthesisPromise.catch(rejectOnce);
        },
      );
    } catch (error) {
      if (
        requestId &&
        isProgressiveResponseCancelled(
          requestId,
        )
      ) {
        return null;
      }

      console.error(
        'Could not start TTS stream:',
        error,
      );

      setAssistantAudioStatus(
        'error',
      );
      setAssistantAudioError(
        error instanceof Error
          ? error.message
          : 'Could not start TTS stream.',
      );
      releaseStreamedTextDisplay(
        requestId,
      );

      throw error;
    }
  };

  const enqueueProgressiveTtsSentence = (
    requestId,
    sentence,
  ) => {
    const cleanedSentence =
      sentence.trim();

    if (!cleanedSentence) {
      return (
        progressiveTtsQueuesRef.current.get(
          requestId,
        ) ?? Promise.resolve()
      );
    }
    const responseTiming =
      responseTimingsRef.current.get(
        requestId,
      );

    if (
      responseTiming &&
      responseTiming
        .firstSentenceQueuedAt === null
    ) {
      responseTiming
        .firstSentenceQueuedAt =
          performance.now();
    }

    const existingQueue =
      progressiveTtsQueuesRef.current.get(
        requestId,
      ) ?? Promise.resolve();

    const updatedQueue =
      existingQueue
        .then(async () => {
          if (
            isProgressiveResponseCancelled(
              requestId,
            )
          ) {
            return;
          }

          const activeResponse =
            activeProgressiveResponseRef.current;

          if (
            activeResponse?.requestId ===
            requestId
          ) {
            activeResponse.playbackComplete =
              false;
          }

          await streamAssistantResponse(
            cleanedSentence,
            {
              replace: false,
              requestId,
            },
          );

          if (
            isProgressiveResponseCancelled(
              requestId,
            )
          ) {
            const clients =
              activeTtsClientsByRequestRef
                .current
                .get(requestId);

            for (
              const client
              of [...(clients ?? [])]
            ) {
              client.cancel(
                activeTtsStreamIdRef.current,
              );
            }
          }
        })
        .catch((error) => {
          console.error(
            'Progressive TTS failed:',
            error,
          );
        });

    progressiveTtsQueuesRef.current.set(
      requestId,
      updatedQueue,
    );

    const spokenText =
      spokenResponseTextRef.current.get(
        requestId,
      ) ?? '';

    spokenResponseTextRef.current.set(
      requestId,
      `${spokenText} ${cleanedSentence}`
        .trim(),
    );

    return updatedQueue;
  };

  const finishProgressiveTtsQueue = (
    requestId,
  ) => {
    const queue =
      progressiveTtsQueuesRef.current.get(
        requestId,
      ) ?? Promise.resolve();

    void queue.finally(() => {
      responseSentenceBuffersRef.current.delete(
        requestId,
      );
      spokenResponseTextRef.current.delete(
        requestId,
      );
      progressiveTtsQueuesRef.current.delete(
        requestId,
      );
      streamedResponsesRef.current.delete(
        requestId,
      );

      const activeResponse =
        activeProgressiveResponseRef.current;

      if (
        activeResponse?.requestId ===
        requestId
      ) {
        activeResponse.synthesisComplete =
          true;
        completeProgressiveResponseIfReady();
      }
    });
  };

  const playAssistantResponse = async (
    responseText,
  ) => {
    const cleanedText = responseText?.trim();

    if (!cleanedText) {
      return;
    }

    ttsAbortControllerRef.current?.abort();

    const abortController =
      new AbortController();

    ttsAbortControllerRef.current =
      abortController;

    setAssistantAudioStatus('synthesising');
    setAssistantAudioError('');

    try {
      let audioContext =
        speakAudioContextRef.current;

      if (
        !audioContext ||
        audioContext.state === 'closed'
      ) {
        audioContext = new (
          window.AudioContext ||
          window.webkitAudioContext
        )();

        speakAudioContextRef.current =
          audioContext;
      }

      if (
        audioContext.state === 'suspended'
      ) {
        await audioContext.resume();
      }

      const {
        audioData,
        metadata,
      } = await synthesiseSpeech({
        text: cleanedText,
        signal: abortController.signal,
      });

      if (abortController.signal.aborted) {
        return;
      }

      const decodedAudio =
        await audioContext.decodeAudioData(
          audioData.slice(0),
        );

      if (abortController.signal.aborted) {
        return;
      }

      currentAudio.current?.stop();

      const source =
        audioContext.createBufferSource();

      source.buffer = decodedAudio;
      source.connect(
        audioContext.destination,
      );

      source.onended = () => {
        if (
          currentAudio.current === source
        ) {
          currentAudio.current = null;
          isPlaying.current = false;
          setAssistantAudioStatus('idle');
          notifyPlaybackComplete();
        }
      };

      currentAudio.current = source;
      isPlaying.current = true;

      setLatestTtsMetadata(metadata);
      setAssistantAudioStatus('playing');

      source.start();
    } catch (error) {
      if (
        error instanceof DOMException &&
        error.name === 'AbortError'
      ) {
        return;
      }

      console.error(
        'Assistant speech playback failed:',
        error,
      );

      isPlaying.current = false;
      currentAudio.current = null;

      setAssistantAudioStatus('error');
      setAssistantAudioError(
        error instanceof Error
          ? error.message
          : 'Assistant speech playback failed.',
      );
    } finally {
      if (
        ttsAbortControllerRef.current ===
        abortController
      ) {
        ttsAbortControllerRef.current =
          null;
      }
    }
  };

  const processTurnTranscript = async (
    utterance,
    {
      clearTypedInput = false,
      silenceDurationMs = INITIAL_VAD_SILENCE_MS,
      turnCompletionConfirmed = false,
    } = {},
  ) => {
    const cleanedUtterance = utterance.trim();

    if (
      !cleanedUtterance ||
      turnRequestPendingRef.current
    ) {
      return null;
    }

    turnRequestPendingRef.current = true;
    setTurnRequestPending(true);
    setTurnRequestError('');

    if (clearTypedInput) {
      clearSilenceReevaluationTimer();
      awaitingSpeechContinuationRef.current =
        false;
    }

    try {
      const result = await sendStreamedTurnEvent({
        partialUtterance: cleanedUtterance,
        isSpeechActive: false,
        silenceDurationMs,
        turnCompletionConfirmed,
        debug: true,
      });

      setLatestTurnResult(result);
      setTurnDecision(result.turn.decision);

      if (
        clearTypedInput &&
        result.turn.should_finalise_turn
      ) {
        setTestUtterance('');
      }

      return result;
    } catch (error) {
      console.error('Turn-processing request failed:', error);

      setTurnRequestError(
        error instanceof Error
          ? error.message
          : 'The turn-processing request failed.',
      );

      return null;
    } finally {
      turnRequestPendingRef.current = false;
      setTurnRequestPending(false);
      processCompletedAudioSegmentsRef.current?.();
    }
  };

  const processCompletedAudioSegments = async () => {
    if (processingAudioSegmentsRef.current) {
      return;
    }

    processingAudioSegmentsRef.current = true;

    try {
      while (
        pendingAudioSegmentIdsRef.current.length > 0
      ) {
        if (turnRequestPendingRef.current) {
          break;
        }

        const segmentId =
          pendingAudioSegmentIdsRef.current[0];
        const segmentPayload =
          completedAudioSegmentsRef.current.get(
            segmentId,
          );

        if (!segmentPayload) {
          break;
        }

        pendingAudioSegmentIdsRef.current.shift();
        completedAudioSegmentsRef.current.delete(
          segmentId,
        );

        setAudioStreamStatus('connected');
        setAudioStreamSummary(segmentPayload.stream);

        const segmentTranscript =
          segmentPayload.transcription?.text?.trim() ?? '';
        const silenceDurationMs =
          segmentPayload.silence_duration_ms ??
          INITIAL_VAD_SILENCE_MS;
        const turnCompletionConfirmed = Boolean(
          segmentPayload
            .turn_completion_confirmed,
        );

        setAudioTranscript(segmentTranscript);

        if (!segmentTranscript) {
          continue;
        }

        const accumulatedTranscript =
          appendTranscriptSegment(
            spokenTurnTranscriptRef.current,
            segmentTranscript,
          );

        spokenTurnTranscriptRef.current =
          accumulatedTranscript;
        setAccumulatedSpokenTranscript(
          accumulatedTranscript,
        );

        const result =
          await processTurnTranscriptRef.current?.(
            accumulatedTranscript,
            {
              silenceDurationMs,
              turnCompletionConfirmed,
            },
          );

        if (result?.turn.should_finalise_turn) {
          clearSilenceReevaluationTimer();
          awaitingSpeechContinuationRef.current =
            false;
          spokenTurnTranscriptRef.current = '';
          setAccumulatedSpokenTranscript('');
        } else if (
          result?.turn.decision ===
          'await_more_speech'
        ) {
          awaitingSpeechContinuationRef.current =
            recordingRef.current;

          if (recordingRef.current) {
            scheduleSilenceReevaluation(
              accumulatedTranscript,
            );
          }
        }
      }
    } finally {
      processingAudioSegmentsRef.current = false;
    }
  };

  useEffect(() => {
    processTurnTranscriptRef.current =
      processTurnTranscript;
    processCompletedAudioSegmentsRef.current =
      processCompletedAudioSegments;
  });

  const submitTestUtterance = async () => {
    return processTurnTranscript(
      testUtterance,
      {
        clearTypedInput: true,
      },
    );
  };

  return (
    <div className="application">
      {!started ? (
        <StartScreen loading={loading} handleStartClick={handleStartClick} />
      ) : (
        <MainApp
          started={started}
          recording={recording}
          setRecording={setRecording}
          recordingRef={recordingRef}
          listenAudioContextRef={listenAudioContextRef}
          listenWorkletNodeRef={listenWorkletNodeRef}
          listenSourceRef={listenSourceRef}
          accumulatedAudioRef={accumulatedAudioRef}
          streamRef={streamRef}
          sendChunkToServer={sendChunkToServer}
          audioQueue={audioQueue}
          setIsPlaying={(status) => {
            isPlaying.current = status;
          }}
          isPlaying={isPlaying}
          currentAudio={currentAudio}
          setCurrentAudio={(audio) => {
            currentAudio.current = audio;
          }}
          stopAssistantAudio={
            stopCurrentAssistantResponse
          }
          assistantAudioStatus={
            assistantAudioStatus
          }
          assistantAudioError={
            assistantAudioError
          }
          latestTtsMetadata={
            latestTtsMetadata
          }
          panel={panel}
          tourItinerary={tourItinerary}
          setPanel={setPanel}
          testUtterance={testUtterance}
          setTestUtterance={setTestUtterance}
          submitTestUtterance={submitTestUtterance}
          turnRequestPending={turnRequestPending}
          turnRequestError={turnRequestError}
          turnDecision={turnDecision}
          latestTurnResult={latestTurnResult}
          streamedAssistantResponse={
            streamedAssistantResponse
          }
          onAudioSegmentStart={startAudioSegment}
          onAudioSegmentCandidate={
            evaluateAudioSegmentCandidate
          }
          onAudioSegmentFinalise={
            finaliseAudioSegment
          }
          onAudioSegmentCancel={cancelAudioSegment}
          onVadSpeechStart={handleVadSpeechStart}
          onVadSpeechEnd={handleVadSpeechEnd}
          audioStreamStatus={audioStreamStatus}
          audioStreamSummary={audioStreamSummary}
          audioStreamError={audioStreamError}
          audioTranscript={audioTranscript}
          accumulatedSpokenTranscript={
            accumulatedSpokenTranscript
          }
          latestSmartTurnResult={
            latestSmartTurnResult
          }
        />
      )}
    </div>
  );
}
