import React, { useEffect, useRef, useState } from 'react';
import StartScreen from './StartScreen';
import MainApp from './MainApp';
import { connectToServer, makeServerRequest } from './utils/server_functions';
import { sendTurnBufferEvent } from '../api/conversationApi';
import { AudioStreamClient } from '../api/audioStreamClient';
import { synthesiseSpeech } from '../api/ttsApi';
import { TtsStreamClient } from '../api/ttsStreamClient';
import { calculateRemainingSilenceMs } from '../audio/vadMath';

const FORCED_FINALISATION_SILENCE_MS = 1800;
const INITIAL_VAD_SILENCE_MS = 600;
const BARGE_IN_CONFIRMATION_MS = 200;
const ASSISTANT_DUCK_GAIN = 0.3;
const ASSISTANT_NORMAL_GAIN = 1.0;
const DUCK_RAMP_SECONDS = 0.08;
const RESTORE_RAMP_SECONDS = 0.12;

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
  const [audioStreamStatus, setAudioStreamStatus] = useState('disconnected');
  const [audioStreamSummary, setAudioStreamSummary] = useState(null);
  const [audioStreamError, setAudioStreamError] = useState('');
  const [audioTranscript, setAudioTranscript] = useState('');
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

  const handleVadSpeechStart = () => {
    vadSpeechActiveRef.current = true;
    vadSpeechEndedAtRef.current = null;
    awaitingSpeechContinuationRef.current = false;
    clearSilenceReevaluationTimer();
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
      clearDuckingTimer();
    }
  }, [recording]);

  useEffect(() => {
    assistantAudioStatusRef.current =
      assistantAudioStatus;
  }, [assistantAudioStatus]);

  useEffect(() => {
    return () => {
      clearSilenceReevaluationTimer();
      clearDuckingTimer();

      ttsAbortControllerRef.current?.abort();

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
            setAudioStreamStatus('streaming');
            setAudioStreamSummary(null);
            setAudioTranscript('');
            setAudioStreamError('');
            setTurnRequestError('');
            break;
          case 'audio_stream_complete':
            setAudioStreamStatus('connected');
            setAudioStreamSummary(message.payload);
            break;
          case 'transcription_started':
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
            awaitingSpeechContinuationRef.current =
              false;
            setAudioStreamStatus('connected');
            processCompletedAudioSegmentsRef.current?.();
            break;
          }
          case 'audio_error': {
            const segmentId =
              message.payload?.segment_id;

            if (segmentId) {
              pendingAudioSegmentIdsRef.current =
                pendingAudioSegmentIdsRef.current.filter(
                  (pendingId) => pendingId !== segmentId,
                );
              completedAudioSegmentsRef.current.delete(
                segmentId,
              );
              clearSilenceReevaluationTimer();
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

  const handleStartClick = () => {
    setStarted(true);
    makeServerRequest('introduction');
    setPanel('text');

    if (!speakAudioContextRef.current) {
      speakAudioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 24000,
      });
    }

    speakAudioContextRef.current.resume();
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
    silenceDurationMs = 600,
  ) => {
    try {
      audioStreamClientRef.current?.finaliseSegment({
        silenceDurationMs,
      });
    } catch (error) {
      console.error(
        'Could not finalise audio segment:',
        error,
      );
    }
  };

  const cancelAudioSegment = () => {
    clearSilenceReevaluationTimer();
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

    ttsStreamClientRef.current?.close();
    ttsStreamClientRef.current = null;

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
          case 'playback_started':
            isPlaying.current = true;
            setAssistantAudioStatus(
              'playing',
            );
            break;

          case 'playback_complete':
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
            break;

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
  ) => {
    const cleanedText = responseText?.trim();

    if (!cleanedText) {
      return;
    }

    stopAssistantAudio();
    restoreAssistantAudio();

    setAssistantAudioStatus(
      'synthesising',
    );
    setAssistantAudioError('');
    setLatestTtsMetadata(null);

    try {
      const playerNode =
        await ensureTtsPlayer();

      const ttsClient =
        new TtsStreamClient({
          onStarted: (metadata) => {
            activeTtsStreamIdRef.current =
              metadata.stream_id;

            setLatestTtsMetadata({
              voice:
                metadata.voice_name,
              language:
                metadata.language_code,
              sampleRate:
                metadata.sample_rate,
              characterCount:
                metadata.character_count,
              generationSeconds: 0,
            });
          },

          onAudioChunk: ({
            samples,
          }) => {
            playerNode.port.postMessage(
              {
                type: 'enqueue',
                samples,
              },
              [samples.buffer],
            );
          },

          onComplete: (metadata) => {
            setLatestTtsMetadata(
              (current) => ({
                ...current,
                generationSeconds:
                  metadata
                  .generation_seconds,
                chunkCount:
                  metadata.chunk_count,
                audioBytes:
                  metadata.audio_bytes,
              }),
            );

            playerNode.port.postMessage({
              type: 'complete',
            });
          },

          onError: (error) => {
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
          },

          onClose: () => {
            if (
              ttsStreamClientRef.current ===
              ttsClient
            ) {
              ttsStreamClientRef.current =
                null;
            }
          },
        });

      ttsStreamClientRef.current =
        ttsClient;

      await ttsClient.connect({
        text: cleanedText,
      });
    } catch (error) {
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
    }
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
      const result = await sendTurnBufferEvent({
        partialUtterance: cleanedUtterance,
        isSpeechActive: false,
        silenceDurationMs,
        debug: true,
      });

      setLatestTurnResult(result);
      setTurnDecision(result.turn.decision);

      if (
        result.turn.should_finalise_turn &&
        result.query?.response
      ) {
        void streamAssistantResponse(
          result.query.response,
        );
      }

      if (clearTypedInput && result.query) {
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
            stopAssistantAudio
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
          onAudioSegmentStart={startAudioSegment}
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
        />
      )}
    </div>
  );
}
