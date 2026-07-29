import React, { useRef } from 'react';
import { micOff_chime, micOn_chime } from './AudioPlayer';

const DEFAULT_VAD_SILENCE_MS = 500;

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
  onAudioSegmentStart,
  onAudioSegmentFinalise,
  onAudioSegmentCancel,
  onVadSpeechStart,
  onVadSpeechEnd,
}) {
  const segmentActiveRef = useRef(false);
  const workletMessageChainRef =
    useRef(Promise.resolve());

  const handleWorkletMessage = async (
    message,
  ) => {
    switch (message.type) {
      case 'speech_start': {
        if (segmentActiveRef.current) {
          return;
        }

        onVadSpeechStart?.();
        await onAudioSegmentStart?.();

        segmentActiveRef.current = true;

        const preRollFrames =
          message.preRollFrames ?? [];

        for (const frame of preRollFrames) {
          const float32 =
            frame instanceof Float32Array
              ? frame
              : new Float32Array(frame);

          sendChunkToServer(
            floatTo16BitPCM(float32),
          );
        }

        return;
      }

      case 'audio_frame': {
        if (!segmentActiveRef.current) {
          return;
        }

        const float32 =
          message.samples instanceof Float32Array
            ? message.samples
            : new Float32Array(
                message.samples,
              );

        sendChunkToServer(
          floatTo16BitPCM(float32),
        );

        return;
      }

      case 'speech_end': {
        onVadSpeechEnd?.(
          message.silenceDurationMs ??
            DEFAULT_VAD_SILENCE_MS,
        );

        if (!segmentActiveRef.current) {
          return;
        }

        segmentActiveRef.current = false;

        onAudioSegmentFinalise?.(
          message.silenceDurationMs ??
            DEFAULT_VAD_SILENCE_MS,
        );

        return;
      }

      default:
        console.warn(
          'Unknown recorder worklet message:',
          message,
        );
    }
  };

  const startListening = async () => {
    if (recordingRef.current === true) {
      return;
    }

    let stream = null;

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

      const source =
        audioContext.createMediaStreamSource(stream);
      listenSourceRef.current = source;

      const node =
        new AudioWorkletNode(audioContext, 'pcm-recorder');
      listenWorkletNodeRef.current = node;

      node.port.onmessage = (event) => {
        workletMessageChainRef.current =
          workletMessageChainRef.current
            .then(() => {
              return handleWorkletMessage(
                event.data,
              );
            })
            .catch((error) => {
              console.error(
                'Could not process recorder message:',
                error,
              );

              onVadSpeechEnd?.(0);

              if (segmentActiveRef.current) {
                segmentActiveRef.current = false;
                onAudioSegmentCancel?.();
              }
            });
      };

      source.connect(node);

      setRecording(true);
      recordingRef.current = true;
      micOn_chime();
    } catch (error) {
      console.error('Could not start recording:', error);

      if (segmentActiveRef.current) {
        segmentActiveRef.current = false;
        onVadSpeechEnd?.(0);
        onAudioSegmentCancel?.();
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
      workletMessageChainRef.current =
        Promise.resolve();
    }
  };

  const stopListening = async () => {
    console.log('stopped listening');
    micOff_chime();
    if (recordingRef.current !== true) return;

    recordingRef.current = false;
    setRecording(false);

    try {
      streamRef.current
        ?.getTracks()
        .forEach((track) => {
          track.stop();
        });

      listenSourceRef.current?.disconnect();
      listenWorkletNodeRef.current?.disconnect();

      await workletMessageChainRef.current;

      if (segmentActiveRef.current) {
        segmentActiveRef.current = false;
        onVadSpeechEnd?.(0);
        onAudioSegmentFinalise?.(0);
      }

      const audioContext =
        listenAudioContextRef.current;

      if (
        audioContext &&
        audioContext.state !== 'closed'
      ) {
        await audioContext.close();
      }

      accumulatedAudioRef.current = [];
      listenSourceRef.current = null;
      listenWorkletNodeRef.current = null;
      listenAudioContextRef.current = null;
      streamRef.current = null;

      workletMessageChainRef.current =
        Promise.resolve();
    } catch (error) {
      console.error(
        'Error stopping recording:',
        error,
      );
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
