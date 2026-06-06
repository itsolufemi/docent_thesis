//import 'web-streams-polyfill/ponyfill'; // Import the polyfill
import React, { useState, useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, Dimensions } from 'react-native';
import { createStackNavigator } from '@react-navigation/stack';
import { NavigationContainer } from '@react-navigation/native';
import { Audio } from 'expo-av'; 
import Recorder from './Recorder';
import AudioPlayer from './AudioPlayer';

export default function MainApplication() {
  const [loading, setLoading] = useState(true); // Tracks loading state
  const [start, setStart] = useState(false); // start application
  const intro_audio = useRef(null); // introduction audio url

  const audioQueue = useRef([]); // audio queue array
  const currentAudio = useRef(null); // To track the current Audio instance
  const isPlaying = useRef(false); // To track if audio is currently playing
  const [asstResponding, setAsstResponding] = useState(true); // tracker for assistant response

  const [panel, setPanel] = useState('text'); // initialize with text panel
  const [transcription, setTranscription] = useState(''); // transcription panel
  const [tourGuide, setTourGuide] = useState(''); // initialize tour section
  const [tourReq, setTourReq] = useState(false); // tracker for tour request status
  const server = 'http://192.168.1.235:5000'; // server url


  //#region helper function
  useEffect(() => {//fetch the introduction on app load
    fetchIntroduction();
  }, []);

  const handleSetAsstResponding = (status) => { //set asst responding ?
    setAsstResponding(status);
    console.log('asstResponding????:', asstResponding);
  };

  const handleStartClick = () => { // when user clicks start button
    queueAudio(intro_audio.current);
    setStart(true);
  };
  //#endregion 
  
  //#region server functions
  const fetchIntroduction = async () => {
    try {
      const response = await fetch(`${server}/intro--duction`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch introduction');
      }

      const res = await response.json();
      setTranscription(res.text); // Set the transcription with the introduction text
      intro_audio.current = res.value; // Set the introduction audio url
      setLoading(false); // loading complete
    } catch (error) {
      console.error('Error fetching introduction:', error);
      setLoading(false);
    }
  };

  const processTour = async () => {
    setPanel('tour'); // Show the tour text section
    handleSetAsstResponding(true); // Assistant is responding

    if (tourReq) return;

    setTourReq(true); // Set tour request to true
    setTourGuide('Loading tour...');

    try {
      const response = await fetch(`${server}/tour`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        throw new Error('Network response was not ok');
      }

      const tourRes = await response.json();
      audioQueue.current = []; // Clear any previous audio
      setTourGuide(tourRes.text); // Update tour guide section with tour text
      queueAudio(tourRes.value); // Add tour audio to the queue
    } catch (error) {
      console.error('Error starting tour:', error);
    }
  };

  const processAudio = async (blob) => {
    audioQueue.current = []; // Clear the audio queue
    handleSetAsstResponding(true);
  
    const reader = new FileReader(); // Initialize FileReader to convert blob to base64
  
    reader.onloadend = async () => {
      const base64data = reader.result.split(',')[1]; // get the base64 string (excluding "data:audio/...;base64,")

      const payload = JSON.stringify({
        audio: base64data, // The base64 audio data
        type: blob.type, // Keep the audio type (e.g., "audio/wav" or "audio/webm")
      });
  
      try {
        const response = await fetch(`${server}/upload-base64`, { // fetch request to the server to process question and get assistant response
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: payload, // Send the base64 payload
        });

        const reader = response.body.getReader(); // Read the streamed response
        const decoder = new TextDecoder('utf-8');
        let result;
  
        setPanel('text'); // Show the text panel
        setTranscription('Loading...');
  
        while (!(result = await reader.read()).done) {
          const chunk = decoder.decode(result.value, { stream: true }); // Decode the response stream
          const lines = chunk.split('\n').filter((line) => line.trim()); // Split into lines and filter empty lines
  
          for (let line of lines) {
            try {
              const parsed = JSON.parse(line); // Parse the JSON line
  
              if (parsed.type === 'transcription') {
                setTranscription(parsed.value + '\n'); // Update transcription
              }
              if (parsed.type === 'audio') {
                queueAudio(parsed.value); // Add audio URL to queue
                setTranscription((prev) => prev + parsed.text); // Append transcription text
              }
              if (parsed.type === 'cancelled') {
                setTranscription('Cancelled.');
                break;
              }
            } catch (error) {
              console.error('Error parsing line:', line, error);
            }
          }
        }
      } catch (error) {
        console.error('Error getting response:', error);
        setTranscription('Error getting response');
      }
    };
  
    reader.readAsDataURL(blob); // convert blob to base64
  };
  

  //#endregion

  //#region audio functions
  const queueAudio = (audioUrl) => {
    audioQueue.current.push(audioUrl); // Add the audio to the queue
    if (!isPlaying.current) {
      playNextAudio(); // Play the audio if not already playing
    }
  };

  const playNextAudio = async () => {
    if (audioQueue.current.length === 0) {
      isPlaying.current = false;
      handleSetAsstResponding(false); // Set assistant responding to false when audio ends
      return;
    }

    isPlaying.current = true; // audio is playing ? yes
    const audioUrl = audioQueue.current.shift(); // set the first element in the array as the next audio to play 

    const { sound } = await Audio.Sound.createAsync(
        { uri: audioUrl },
        { shouldPlay: true }
    );
    
    currentAudio.current = sound;
    sound.playAsync();
   
    sound.setOnPlaybackStatusUpdate((status) => {
        if (status.didJustFinish) {
          isPlaying.current = false;
          playNextAudio(); // Play next audio when current audio ends
        };

        if (status.error) {
        console.error('Error playing audio');
        isPlaying.current = false;
        stopAudio(); // Stop the audio if there is an error
        };
    });
  };

  const stopAudio = () => { //to stop the audio
    if (currentAudio.current) {
      currentAudio.current.stopAsync();
      console.log('audio stopped');
      currentAudio.current = null;
    }

    isPlaying.current = false;
    return;
  };

  const stop_run = async () => {
    console.log('Stopping assistant stream/run...');
    handleSetAsstResponding(false); // Set assistant responding to false
    audioQueue.current = []; // Clear the audio queue
    stopAudio(); // Stop the audio playing

    try {
      const response = await fetch(`${server}/cancel-run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        throw new Error('Network response was not ok');
      }

      const result = await response.json();
      console.log('Canceled run result:', result);
    } catch (error) {
      console.error('Error cancelling run:', error);
    }
  };
  //#endregion 



  //#region application interface components
  const StartScreen = () => ( // start screen 
    <View style={styles.section}>
      <TouchableOpacity
        style={[styles.roundButton, loading && styles.greenBtn]}
        disabled={loading}
        onPress={handleStartClick}
      >
        <Text style={styles.icon}>{loading ? '...' : '▶'}</Text>
      </TouchableOpacity>
    </View>
  );

  const MainAppHeader = () => ( // app header component
    <View style={styles.section && styles.player}>
      {!asstResponding ? (
        <Recorder onAudioProcessed={processAudio} />
      ) : (
        <AudioPlayer
          audioQueueLength={audioQueue.current.length}
          isPlaying={isPlaying.current}
          stop_run={stop_run}
          playNextAudio={playNextAudio}
        />
      )}
    </View>
  );

  const MainAppTextPanel = () => ( // text panel component
    <ScrollView style={styles.section && styles.textPanel}>
      <Text>{panel === 'text' ? transcription : tourGuide}</Text>
    </ScrollView>
  );

const MainApp = () => ( // main application component
    <View style={styles.main}>
        <MainAppHeader />
        <MainAppTextPanel />
        <View style={styles.navigation}>
            <TouchableOpacity onPress={processTour} style={styles.navButton}>
                <Text style={styles.icon}>Tour</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.navButton}>
                <Text style={styles.icon}>📷</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setPanel('text')} style={styles.navButton}>
                <Text style={styles.icon}>CC</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.closeButton}>
                <Text style={styles.icon}>X</Text>
            </TouchableOpacity>
        </View>
    </View>
);
  //#endregion
  
  //#region navigator
  const Stack = createStackNavigator(); // stack navigator for start screen and main application
  const AppStackNav = () => (
    <Stack.Navigator>
      {!start ? 
      <Stack.Screen 
        name="StartScreen" 
        component={StartScreen} 
        options={{ headerShown: false }} // Hide header
      /> : 
      <Stack.Screen 
        name="MainApp" 
        component={MainApp} 
        options={{ headerShown: false }} // Hide header
      /> }
    </Stack.Navigator>
  );

  //#endregion


  return ( // main application component implemented
    <View style={{ flex: 1 }}>
        <NavigationContainer>
            <AppStackNav />
        </NavigationContainer>   
    </View>
  );
}

const { width, height } = Dimensions.get('window'); // window dimensions

const styles = StyleSheet.create({
  main: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    width: '100%',
    backgroundColor: 'rgba(255, 255, 255, 0.93)',
  },

  section: {
    marginTop: 20,
    marginBottom: 20,
    alignItems: 'center',
    width: '100%',
  },

  player: {
  },

  roundButton: {
    borderColor: 'rgba(255, 255, 255, 0.5)',
    borderWidth: 0.5,
    backgroundColor: 'transparent',
    borderRadius: 50,
    padding: 10,
    width: 45,
    height: 45,
    justifyContent: 'center',
    alignItems: 'center',
  },

  greenBtn: {
    backgroundColor: 'seagreen',
  },

  icon: {
    color: 'black',
    fontSize: 15,
    fontWeight:'600',
  },

  textPanel: {
    height:height * 0.7,
    maxHeight: 600,
    overflow: 'auto',
    padding: 20,
    width: '100%',
    textAlign: 'justify',
  },

  navigation: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 30,
    alignItems: 'center',
    position: 'absolute',
    bottom: 0,
    width: '100%',
  },

  navButton: {
    width: 50,
    height: 30,
    margin: 10,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f0f0f0',
    borderRadius: 5,
    borderWidth: 0.3,
    borderColor: 'green',
  },
  closeButton: {
    backgroundColor: 'rgb(94, 31, 31)',
    width: 50,
    height: 30,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 5,
  },
});
