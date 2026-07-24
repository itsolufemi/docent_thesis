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
  testUtterance,
  setTestUtterance,
  submitTestUtterance,
  turnRequestPending,
  turnRequestError,
  turnDecision,
  latestTurnResult,
  onAudioStreamStart,
  onAudioStreamStop,
  audioStreamStatus,
  audioStreamSummary,
  audioStreamError,
  audioTranscript,
  accumulatedSpokenTranscript,
}) {
  const [questionTranscript, setQuestionTranscript] = useState('');
  const [caption, setCaption] = useState('');

  setCaptionFunctionsinServer({
    handleSetCaption: setCaption,
    handleSetQuestion_trans: setQuestionTranscript,
  });

  React.useEffect(() => {
    if (!latestTurnResult) {
      return;
    }

    const finalisedUtterance =
      latestTurnResult.turn?.finalised_utterance;

    if (finalisedUtterance) {
      setQuestionTranscript(finalisedUtterance);
    }

    const assistantResponse = latestTurnResult.query?.response;

    if (assistantResponse) {
      setCaption(assistantResponse);
    }
  }, [latestTurnResult]);

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
          onAudioStreamStart={onAudioStreamStart}
          onAudioStreamStop={onAudioStreamStop}
          disabled={turnRequestPending}
        />
        <AudioPlayer
          speakAudioContextRef={speakAudioContextRef}
          speakWorkletRef={speakWorkletRef}
          stopRun={stopRun}
          notifyPlaybackComplete={notifyPlaybackComplete}
        />
      </header>

      <section className="audio-stream-debug">
        <p>Audio stream: {audioStreamStatus}</p>

        {audioStreamSummary && (
          <>
            <p>
              Chunks: {audioStreamSummary.chunk_count}
            </p>
            <p>
              Bytes: {audioStreamSummary.total_bytes}
            </p>
            <p>
              Duration:{' '}
              {audioStreamSummary.duration_seconds.toFixed(2)}{' '}
              seconds
            </p>
          </>
        )}

        {audioTranscript && (
          <p>Transcript: {audioTranscript}</p>
        )}

        {accumulatedSpokenTranscript && (
          <p>
            Current spoken turn:{' '}
            {accumulatedSpokenTranscript}
          </p>
        )}

        {audioStreamError && (
          <p className="turn-test-error">
            {audioStreamError}
          </p>
        )}
      </section>

      <form
        className="turn-test-form"
        onSubmit={(event) => {
          event.preventDefault();
          submitTestUtterance();
        }}
      >
        <label htmlFor="turn-test-input">
          Test the conversation engine
        </label>

        <div className="turn-test-controls">
          <input
            id="turn-test-input"
            type="text"
            value={testUtterance}
            onChange={(event) => {
              setTestUtterance(event.target.value);
            }}
            placeholder="Type an utterance"
            disabled={turnRequestPending}
          />

          <button
            type="submit"
            disabled={
              turnRequestPending ||
              testUtterance.trim().length === 0
            }
          >
            {turnRequestPending ? 'Sending…' : 'Send'}
          </button>
        </div>

        {turnDecision && (
          <p className="turn-test-status">
            Turn decision: {turnDecision}
          </p>
        )}

        {turnRequestError && (
          <p className="turn-test-error">
            {turnRequestError}
          </p>
        )}
      </form>

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
