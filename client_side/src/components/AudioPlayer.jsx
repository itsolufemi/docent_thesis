import React, { useEffect } from 'react';
import { setAudioFunctionsinServer } from './utils/server_functions';
import { ipv4 } from './utils/ipv4_module';

console.log('using AudioPlayer.js');

export default function AudioPlayer({
  speakAudioContextRef,
  speakWorkletRef,
  notifyPlaybackComplete,
  stopRun,
}) {
  useEffect(() => {
    if (!speakAudioContextRef.current) return;

    async function setupAudioWorklet() {
      const url = `http://${ipv4}:5000/worklets/pcm-player.worklet.js`;
      await speakAudioContextRef.current.audioWorklet.addModule(url);
      const node = new AudioWorkletNode(speakAudioContextRef.current, 'pcm-player');
      node.connect(speakAudioContextRef.current.destination);
      speakWorkletRef.current = node;

      node.port.onmessage = (event) => {
        if (event.data.type === 'playback_complete') {
          console.log('playback complete message received in AudioPlayer');
          notifyPlaybackComplete();
        }
      };

      setAudioFunctionsinServer({
        enqueuePCM: (pcm16) => {
          speakWorkletRef.current?.port.postMessage(pcm16);
        },
        msg_audioStreamComplete: () => {
          speakWorkletRef.current?.port.postMessage({ end: true });
        },
        stopAudio: () => {
          speakWorkletRef.current?.port.postMessage({ flush: true });
        },
      });
    }

    setupAudioWorklet();
  }, [notifyPlaybackComplete, speakAudioContextRef, speakWorkletRef]);

  const handlePause = () => {
    console.log('Pause button clicked');
    stopRun();
    speakWorkletRef.current?.port.postMessage({ flush: true });
  };

  return (
    <button type="button" onClick={handlePause} className="player-button stop-button">
      ■
    </button>
  );
}

export const micOn_chime = () => {
  const audio = new Audio(`http://${ipv4}:5000/chimes/on.wav`);
  audio.play().catch((err) => console.warn('chime-on error:', err));
};

export const micOff_chime = () => {
  const audio = new Audio(`http://${ipv4}:5000/chimes/off.wav`);
  audio.play().catch((err) => console.warn('chime-off error:', err));
};
