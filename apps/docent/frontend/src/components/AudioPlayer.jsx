import React from 'react';
import { chimes } from './utils/lib/chimes';


export default function AudioPlayer({
  stopAssistantAudio,
  assistantAudioStatus,
}) {
  const canStop =
    assistantAudioStatus ===
      'synthesising' ||
    assistantAudioStatus ===
      'playing';

  return (
    <button
      type="button"
      onClick={stopAssistantAudio}
      disabled={!canStop}
      className="player-button stop-button"
      aria-label="Stop assistant speech"
    >
      ■
    </button>
  );
}


function playChime(audioData) {
  const audio = new Audio(
    `data:audio/wav;base64,${audioData}`,
  );

  audio.play().catch((error) => {
    console.warn(
      'Could not play microphone chime:',
      error,
    );
  });
}


export const micOn_chime = () => {
  playChime(chimes.start);
};


export const micOff_chime = () => {
  playChime(chimes.stop);
};
