import React, { useState } from 'react';
import Recorder from './Recorder';
import AudioPlayer from './AudioPlayer';
import { setCaptionFunctionsinServer } from './utils/server_functions';

export default function MainApp({
  recording,
  setRecording,
  recordingRef,
  listenAudioContextRef,
  listenWorkletNodeRef,
  listenSourceRef,
  accumulatedAudioRef,
  streamRef,
  sendChunkToServer,
  notifyPlaybackComplete,
  speakAudioContextRef,
  speakWorkletRef,
  stopRun,
  panel,
  tourItinerary,
  setPanel,
}) {
  const [questionTranscript, setQuestionTranscript] = useState('');
  const [caption, setCaption] = useState('');

  setCaptionFunctionsinServer({
    handleSetCaption: setCaption,
    handleSetQuestion_trans: setQuestionTranscript,
  });

  return (
    <div className="main-app">
      <header className="player-controls">
        <Recorder
          recording={recording}
          setRecording={setRecording}
          recordingRef={recordingRef}
          listenAudioContextRef={listenAudioContextRef}
          listenWorkletNodeRef={listenWorkletNodeRef}
          listenSourceRef={listenSourceRef}
          accumulatedAudioRef={accumulatedAudioRef}
          streamRef={streamRef}
          sendChunkToServer={sendChunkToServer}
        />
        <AudioPlayer
          speakAudioContextRef={speakAudioContextRef}
          speakWorkletRef={speakWorkletRef}
          stopRun={stopRun}
          notifyPlaybackComplete={notifyPlaybackComplete}
        />
      </header>

      <section className="text-panel">
        <p className="question-box">
          {panel === 'text' ? questionTranscript : 'Tour Itinerary'}
        </p>
        <p className="caption-text">
          {panel === 'text' ? caption : tourItinerary}
        </p>
      </section>

      <nav className="bottom-nav" aria-label="Application panels">
        <button
          type="button"
          className="nav-button"
          onClick={() => setPanel('tour')}
          disabled={!tourItinerary}
        >
          Tour
        </button>
        <button type="button" className="nav-button" disabled>
          Camera
        </button>
        <button type="button" className="nav-button" onClick={() => setPanel('text')}>
          CC
        </button>
        <button type="button" className="close-button">
          X
        </button>
      </nav>
    </div>
  );
}
