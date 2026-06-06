import React, { useRef, useEffect } from 'react';
import { createAudioPlayer, Audio, useAudioPlayerStatus} from 'expo-audio';
import { chimes } from './utils/chimes'; // import the chimes audio file
import { TouchableOpacity, Text, StyleSheet } from 'react-native';
import { setAudioFunctionsinServer } from './utils/server_functions';
import * as FileSystem from 'expo-file-system';
import { Platform } from 'react-native';

const saveBase64ToFile = async (base64Wav) => { // Function to save base64 string to a file
  const fileUri = `${FileSystem.cacheDirectory}-audio-${Date.now()}.wav`;
  await FileSystem.writeAsStringAsync(fileUri, base64Wav, {
    encoding: FileSystem.EncodingType.Base64,
  });
  return fileUri;
};

export const playchime =  async (toggle) => { // Function to play the chimes audio
  let uri;
  try {
    const player = createAudioPlayer();
    if (toggle === 'on') { //toggle on
      if(Platform.OS !== 'web') { // mobile
        uri = await saveBase64ToFile(chimes.start);
        //console.log('Played start chime:');
      } else { // For web, use the base64 string directly
        uri = `data:audio/wav;base64,${chimes.start}`;
      } 
    } else { //toggle off
      if(Platform.OS !== 'web') { // mobile
        uri = await saveBase64ToFile(chimes.stop);
        //console.log('Played stop chime:');
      } else { // For web, use the base64 string directly
        uri = `data:audio/wav;base64,${chimes.stop}`;
      }
    }
    player.replace(uri);
    player.play();

    const status = setInterval(() => { // Check the status of the player every 10ms
      try {
        const currentStatus = player.currentStatus;
        if (currentStatus && currentStatus.duration > 0 && currentStatus.currentTime >= currentStatus.duration && !currentStatus.playing) {
          //console.log('Chime playback finished');
          clearInterval(status); // Clear the interval after playback is finished
          player.remove?.(); // Remove the player after playback
        }
      } catch (error) {
        console.error('Error checking player status:', error);
      }
    }, 10);
    return;
  } catch (error) {
    console.error('Error playing chime:', error);
  }
}

const AudioPlayer = ({ start, intro_audio, setIntroAudio,audioQueue, setIsPlaying, handleSetAsstResponding, isPlaying, setCurrentAudio, reqStopRun}) => {
  useEffect(() => { //configure the audio mode when the component mounts
    const configureAudioMode = async () => {
      try {
        await Audio.setAudioModeAsync({
          allowsRecordingIOS: true,
          playsInSilentModeIOS: true,
          staysActiveInBackground: true,
          //shouldDuckAndroid: true,
          //interruptionModeIOS: Audio.INTERRUPTION_MODE_IOS_DO_NOT_MIX,
          //interruptionModeAndroid: Audio.INTERRUPTION_MODE_ANDROID_DO_NOT_MIX,
        });
        console.log('Audio mode configured');
      } catch (error) {
        console.warn('Error setting audio mode:', error);
      }
    };

    configureAudioMode();
  }, []);

  const curr_Audio = useRef(null); // global variable to store the current audio object
  const currentPlayer = useRef(null);
  const player_status_check_interval = useRef(null);

  useEffect(() => { //ensure that the intro audio isnt queued/played until the start state is updated by the user clicking the start button
    if(start && intro_audio.current.length > 0) {
      queueAudio(intro_audio.current); // queue the introduction audio
      setIntroAudio([]); // clear the introduction audio after queuing
    }
  }, [start]);
 
  const queueAudio = async (base64Wav) => {
    try {
      let uri;
      if (Platform.OS !== 'web') { //for mobile save the base64 string to a file
        uri = await saveBase64ToFile(base64Wav); 
      } else { // For web, use the base64 string directly
        uri = `data:audio/wav;base64,${base64Wav}`;
      }
      const player = createAudioPlayer();
      player.replace(uri);
      //console.log('player:', player);
      audioQueue.current.push({ uri, player });

      if (!isPlaying.current) {
        playNextAudio();
      }
    } catch (error) {
      console.error('Error preloading audio:', error);
    }
  };

  const playNextAudio = async () => {
    try {
      if (player_status_check_interval.current) {
        clearInterval(player_status_check_interval.current);
      }

      if (audioQueue.current.length === 0) {
        setIsPlaying(false);
        //handleSetAsstResponding(false);
        setCurrentAudio(null);
        curr_Audio.current = null;
        return;
      }

      const { uri, player } = audioQueue.current.shift();
      curr_Audio.current = uri;
      currentPlayer.current = player;
      setCurrentAudio(uri);
      setIsPlaying(true);

      await player.play();

      player_status_check_interval.current = setInterval(async () => {
        try {
          const status = await player?.currentStatus;

          if (
            status &&
            status.duration > 0 &&
            status.currentTime >= status.duration &&
            !status.playing
          ) {
            clearInterval(player_status_check_interval.current);  
            //console.log('Playback status:', status);
            await player.remove?.();
            setIsPlaying(false);
            playNextAudio();
          }
        } catch (error) {
          console.error('Error in playback status check:', error);
          clearInterval(player_status_check_interval.current);
        }
      }, 100);
    } catch (error) {
      console.error('Error playing audio:', error);
      setIsPlaying(false);
    }
  };

  const stopAudio = async () => { //to stop the audio
    try {
      if (curr_Audio.current && currentPlayer) {
        await currentPlayer.current.pause();
        audioQueue.current = [];
        await currentPlayer.current.remove?.();
        setCurrentAudio(null);
        curr_Audio.current = null;
        setIsPlaying(false);
        if (player_status_check_interval.current) {
          clearInterval(player_status_check_interval.current);
        }
      }

      audioQueue.current.length = 0;

    } catch (error) {
      console.error('Error stopping audio:', error);
    }
  };

  setAudioFunctionsinServer({queueAudio, stopAudio}); // set the audio functions in the server

  return (
    <TouchableOpacity onPress={isPlaying ? reqStopRun : playNextAudio} style={styles.button}>
        <Text style={isPlaying ? styles.stopIcon : styles.playIcon}>
            {audioQueue.current.length === 0 || isPlaying ? '❚❚' : '▶'}
        </Text>
    </TouchableOpacity>
  );
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
  playIcon: {
    fontSize: 18, // Adjust the icon size as per your design
    color: '#000',
  },
  stopIcon: {
    fontSize: 13,
    color: '#ff0000', // Red color for stop button
  },
});

export default AudioPlayer;
