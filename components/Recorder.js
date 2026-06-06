import React, { useRef, useState, useEffect } from "react";
import { styles } from './styles/styles';
import { TouchableOpacity, View, Text, Platform } from 'react-native';
import { ipv4 } from './utils/ipv4_module';
import { micOn_chime, micOff_chime } from './AudioPlayer';

//console.log("using recorder.web.js");

//#region helper functions
function floatTo16BitPCM(float32Array) {
  const buffer = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buffer);
  let offset = 0;
  for (let i = 0; i < float32Array.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Uint8Array(buffer);
}

function encodeWav(samples, sampleRate = 16000) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  // RIFF header
  const writeString = (view, offset, str) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  return new Blob([view], { type: "audio/wav" });
}
//#endregion

export default function Recorder({recording, handleSetRecording, recordingRef, ac_ref_listen, workletNodeRef_listen, sourceRef, accumulatedRef, streamRef, reqSendChunksToServer, }) {
  useEffect(() => {
  //return () => console.log("Recorder unmounted");
}, []);

  const startListening = async () => { //start recording
    micOn_chime();
    if (recordingRef.current === true) return; // if already recording, do nothing
    console.log('listening');
    // update your original state + ref

   // await playchime('on'); // play a chime sound when listening starts
    const ac = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 16000,
    });
    ac_ref_listen.current = ac;

    // load worklet from backend static server
    const url = `http://${ipv4}:5000/worklets/recorder.worklet.js`;
    await ac.audioWorklet.addModule(url);

    //get mic input
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;

    const src = ac.createMediaStreamSource(stream);
    sourceRef.current = src;

    const node = new AudioWorkletNode(ac, "pcm-recorder");
    workletNodeRef_listen.current = node;

    node.port.onmessage = (event) => {
      const float32 = event.data;         // Float32Array mono
      accumulatedRef.current.push(float32);
      const pcm16 = floatTo16BitPCM(float32);      
      reqSendChunksToServer(pcm16);//send chunk to server
    };

    // capture only (avoid feedback): do NOT connect to destination
    src.connect(node);

    handleSetRecording(true);
    recordingRef.current = true;
  };

  const stopListening = async () => {
    // idempotent guard using your ref name
    console.log('stopped listening');
    micOff_chime();
    if (recordingRef.current !== true) return; // if not recording, do nothing
    recordingRef.current = false;
    handleSetRecording(false); 

    try {
  //  try { await playchime('off'); } catch (e) { console.warn(e); }

    // 1) stop mic trackson
    if (streamRef.current) {
      try {
        streamRef.current.getTracks().forEach(t => t.stop());
      } catch { /* ignore */ }
    }

    // 2) disconnect nodes safely
    try { sourceRef.current?.disconnect(); } catch {}
    try { workletNodeRef_listen.current?.disconnect(); } catch {}

    // 3) close AudioContext if still open
    const ac = ac_ref_listen.current;
    if (ac && ac.state !== "closed") {
      try { await ac.close(); } catch {}
    }

    // 4) flatten Float32 chunks (no .flat on typed arrays)
    let wavBlob = null;
    const chunks = accumulatedRef.current;
    if (chunks.length) {
      const total = chunks.reduce((n, arr) => n + arr.length, 0);
      const flat = new Float32Array(total);
      let o = 0;
      for (const c of chunks) { flat.set(c, o); o += c.length; }
      wavBlob = encodeWav(flat, 16000);
    }

     // 5) clear refs
    accumulatedRef.current = [];
    sourceRef.current = null;
    workletNodeRef_listen.current = null;
    ac_ref_listen.current = null;
    streamRef.current = null;
    } catch (error) {
      console.error('Error stopping recording:', error);
    }
  };


  return (
    <TouchableOpacity
    onPress={recording ? stopListening : startListening}
    style={[styles.micButton, styles.button, recording && styles.recordingButton]}
    >
        <Text style={styles.icon}>
        {recording ? '🎙️' : '🎙️'}
        </Text>
    </TouchableOpacity>
  );
}
