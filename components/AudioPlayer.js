import React, { useEffect, useRef } from 'react';
import { TouchableOpacity, Text, StyleSheet } from 'react-native';
import { setAudioFunctionsinServer } from "./utils/server_functions";
import { ipv4 } from './utils/ipv4_module';

console.log("using AudioPlayer.web.js");

export default function AudioPlayerWeb({ac_ref_speak, workLetRef_speak, reqNotifyPlaybackComplete, reqStopRun }) {
  useEffect(() => {
    if (!ac_ref_speak.current) return;  // context was created in MainApplication

    (async () => {
      const url = `http://${ipv4}:5000/worklets/pcm-player.worklet.js`;
      await ac_ref_speak.current.audioWorklet.addModule(url);
      const node = new AudioWorkletNode(ac_ref_speak.current, "pcm-player");
      node.connect(ac_ref_speak.current.destination);
      workLetRef_speak.current = node;

      node.port.onmessage = (event) => {
        if (event.data.type === 'playback_complete') {
          console.log('playback complete message received in AudioPlayer');
          reqNotifyPlaybackComplete(); // notify MainApplication that playback is complete so that it can update the server
        }
      };

      setAudioFunctionsinServer({ // sending the following function to the 'server_functions' module to handle audio chunks from the server
        enqueuePCM: (pcm16) => { // function to enqueue PCM chunks to the AudioWorkletNode
          workLetRef_speak.current?.port.postMessage(pcm16);
        },

        msg_audioStreamComplete: () => { // function to notify the AudioWorkletNode that the stream has ended
          workLetRef_speak.current?.port.postMessage({ end: true });
        },

        stopAudio: () => { // clear queue by sending a flush signal alongside sending a cancel message to the server
          workLetRef_speak.current?.port.postMessage({ flush: true });
        }
      });
    })();

    return () => {
      // don’t close here — context is owned by MainApplication
    };
  }, []);
  

  const handlePause = () => {
    console.log("Pause button clicked");
    // tell server to cancel
    reqStopRun();
    // flush audio buffer locally
    workLetRef_speak.current?.port.postMessage({ flush: true });
    //setIsPlaying(false);
  };

  return  (
    <TouchableOpacity onPress={ handlePause } style={styles.button}>
        <Text style={styles.icon}>
            ⏹
        </Text>
    </TouchableOpacity>
  );
}

export const micOn_chime = () => {
  const audio = new Audio(`http://${ipv4}:5000/chimes/on.wav`);  // place this file in your public/ folder
  audio.play().catch(err => console.warn("chime-on error:", err));
};

export const micOff_chime = () => {
  const audio = new Audio(`http://${ipv4}:5000/chimes/off.wav`); // place this file in your public/ folder
  audio.play().catch(err => console.warn("chime-off error:", err));
};

const styles = StyleSheet.create({
  button: {
    borderColor: 'rgba(255, 255, 255, 0.5)',
    borderWidth: 0.5,
    backgroundColor: 'transparent',
    borderRadius: 50,
    padding: 10,
    width: 30,
    height: 30,
    justifyContent: 'center',
    alignItems: 'center',
    boxShadow: '0px 0px 20px rgba(0, 0, 0, 0.5)',
    transition: 'all 0.3s ease-in-out',
  },
  icon: {
    fontSize: 15, // Adjust the icon size as per your design
    color: '#A62A12',
  },
});
