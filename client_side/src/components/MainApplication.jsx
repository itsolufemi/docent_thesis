import React, { useEffect, useRef, useState } from 'react';
import StartScreen from './StartScreen';
import MainApp from './MainApp';
import { connectToServer, makeServerRequest } from './utils/server_functions';
import { sendTurnBufferEvent } from '../api/conversationApi';

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
    makeServerRequest('chunk', chunk);
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
        />
      )}
    </div>
  );
}
