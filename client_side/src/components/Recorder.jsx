import React from 'react';
import { micOff_chime, micOn_chime } from './AudioPlayer';

function floatTo16BitPCM(float32Array) {
  const buffer = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buffer);
  let offset = 0;

  for (let i = 0; i < float32Array.length; i += 1, offset += 2) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  return new Uint8Array(buffer);
}

export default function Recorder({
  recording,
  setRecording,
  recordingRef,
  listenAudioContextRef,
  listenWorkletNodeRef,
  listenSourceRef,
  accumulatedAudioRef,
  streamRef,
  sendChunkToServer,
  onAudioStreamStart,
  onAudioStreamStop,
}) {
  const startListening = async () => {
    if (recordingRef.current === true) {
      return;
    }

    let stream = null;
    let backendStreamStarted = false;

    try {
      console.log('listening');

      const audioContext = new (
        window.AudioContext ||
        window.webkitAudioContext
      )({
        sampleRate: 16000,
      });
      listenAudioContextRef.current = audioContext;

      await audioContext.audioWorklet.addModule(
        '/worklets/recorder.worklet.js',
      );

      stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });
      streamRef.current = stream;

      await onAudioStreamStart?.();
      backendStreamStarted = true;

      const source =
        audioContext.createMediaStreamSource(stream);
      listenSourceRef.current = source;

      const node =
        new AudioWorkletNode(audioContext, 'pcm-recorder');
      listenWorkletNodeRef.current = node;

      node.port.onmessage = (event) => {
        const float32 = event.data;
        accumulatedAudioRef.current.push(float32);
        sendChunkToServer(floatTo16BitPCM(float32));
      };

      source.connect(node);

      setRecording(true);
      recordingRef.current = true;
      micOn_chime();
    } catch (error) {
      console.error('Could not start recording:', error);

      if (backendStreamStarted) {
        onAudioStreamStop?.();
      }

      stream?.getTracks().forEach((track) => {
        track.stop();
      });

      listenSourceRef.current?.disconnect();
      listenWorkletNodeRef.current?.disconnect();

      const audioContext = listenAudioContextRef.current;

      if (
        audioContext &&
        audioContext.state !== 'closed'
      ) {
        await audioContext.close();
      }

      recordingRef.current = false;
      setRecording(false);
      accumulatedAudioRef.current = [];
      listenSourceRef.current = null;
      listenWorkletNodeRef.current = null;
      listenAudioContextRef.current = null;
      streamRef.current = null;
    }
  };

  const stopListening = async () => {
    console.log('stopped listening');
    micOff_chime();
    if (recordingRef.current !== true) return;

    recordingRef.current = false;
    setRecording(false);

    try {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      listenSourceRef.current?.disconnect();
      listenWorkletNodeRef.current?.disconnect();

      const audioContext = listenAudioContextRef.current;
      if (audioContext && audioContext.state !== 'closed') {
        await audioContext.close();
      }

      onAudioStreamStop?.();

      accumulatedAudioRef.current = [];
      listenSourceRef.current = null;
      listenWorkletNodeRef.current = null;
      listenAudioContextRef.current = null;
      streamRef.current = null;
    } catch (error) {
      console.error('Error stopping recording:', error);
    }
  };

  return (
    <button
      type="button"
      onClick={recording ? stopListening : startListening}
      className={`player-button mic-button ${recording ? 'is-recording' : ''}`}
    >
      Mic
    </button>
  );
}
