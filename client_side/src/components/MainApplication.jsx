import React, { useEffect, useRef, useState } from 'react';
import StartScreen from './StartScreen';
import MainApp from './MainApp';
import { connectToServer, makeServerRequest } from './utils/server_functions';
import { sendTurnBufferEvent } from '../api/conversationApi';
import { AudioStreamClient } from '../api/audioStreamClient';

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
  const speakWorkletRef = useRef(null);
  const audioStreamClientRef = useRef(null);

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
          case 'audio_stream_started':
            setAudioStreamStatus('streaming');
            setAudioStreamSummary(null);
            setAudioTranscript('');
            break;
          case 'audio_stream_complete':
            setAudioStreamStatus('connected');
            setAudioStreamSummary(message.payload);
            break;
          case 'transcription_started':
            setAudioStreamStatus('transcribing');
            break;
          case 'audio_transcription':
            setAudioStreamStatus('connected');
            setAudioStreamSummary(message.payload.stream);
            setAudioTranscript(
              message.payload.transcription?.text ?? '',
            );
            break;
          case 'audio_stream_cancelled':
            setAudioStreamStatus('connected');
            break;
          case 'audio_error':
            setAudioStreamError(
              message.payload?.detail ??
              'Unknown audio-stream error.',
            );
            break;
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

  const startAudioStream = async () => {
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
    audioClient.startStream({
      sampleRate: 16000,
      channels: 1,
    });
  };

  const stopAudioStream = () => {
    try {
      audioStreamClientRef.current?.stopStream();
    } catch (error) {
      console.error('Could not stop audio stream:', error);
    }
  };

  const notifyPlaybackComplete = () => {
    makeServerRequest('playback_complete', null);
  };

  const stopRun = () => {
    makeServerRequest('cancel', null);
  };

  const submitTestUtterance = async () => {
    const utterance = testUtterance.trim();

    if (!utterance || turnRequestPending) {
      return null;
    }

    setTurnRequestPending(true);
    setTurnRequestError('');

    try {
      const result = await sendTurnBufferEvent({
        partialUtterance: utterance,
        isSpeechActive: false,
        silenceDurationMs: 500,
        debug: true,
      });

      setLatestTurnResult(result);
      setTurnDecision(result.turn.decision);

      if (result.query) {
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
      setTurnRequestPending(false);
    }
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
          notifyPlaybackComplete={notifyPlaybackComplete}
          speakAudioContextRef={speakAudioContextRef}
          speakWorkletRef={speakWorkletRef}
          currentAudio={currentAudio}
          setCurrentAudio={(audio) => {
            currentAudio.current = audio;
          }}
          stopRun={stopRun}
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
          onAudioStreamStart={startAudioStream}
          onAudioStreamStop={stopAudioStream}
          audioStreamStatus={audioStreamStatus}
          audioStreamSummary={audioStreamSummary}
          audioStreamError={audioStreamError}
          audioTranscript={audioTranscript}
        />
      )}
    </div>
  );
}
