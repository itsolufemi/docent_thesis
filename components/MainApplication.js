//tag: salvage web
import React, { useState, useEffect, useRef } from 'react';
import { View } from 'react-native';
import StartScreen from './StartScreen';
import MainApp from './MainApp';
import { createStackNavigator } from '@react-navigation/stack';
import { NavigationContainer } from '@react-navigation/native';
import {connectToServer, makeServerRequest } from './utils/server_functions';

export default function MainApplication() {
  //#region state variables
  const [loading, setLoading] = useState(true); // Tracks loading state
  const handleSetLoading = (status) => setLoading(status); // Setter function for loading state

  const [start, setStart] = useState(false); // start application this would be used for ui effects i.e updating the the component when the user clicks start button
  const isStartedRef = useRef(false); // To track if the start button has been clicked
  const handleSetStart = (status) => {
    setStart(status); // Setter function for start state
    isStartedRef.current = status; // Update the ref value
  };

  /*
  const intro_audio = useRef([]); // introduction audio url
  const setIntroAudio = (url) => intro_audio.current = url; // Setter function for introduction audio
  */
  const [recording, setRecording] = useState(false);
  const handleSetRecording = (status) => setRecording(status);

  //#region moved the recording ref here so that its value is preserved when recorder component unmounts/remounts
  const recordingRef = useRef(null);
  const ac_ref_listen = useRef(null);
  const workletNodeRef_listen = useRef(null);
  const sourceRef = useRef(null);
  const accumulatedRef = useRef([]);
  const streamRef = useRef(null);
  //#endregion

  const audioQueue = useRef([]); // audio queue array
  const setAudioQueue = (queue) => audioQueue.current = queue; // Setter function for audio queue

  const currentAudio = useRef(null); // To track the current Audio instance
  const setCurrentAudio = (audio) => currentAudio.current = audio; // Setter function for current audio

  const isPlaying = useRef(false); // To track if audio is currently playing
  const setIsPlaying = (status) => isPlaying.current = status; // Setter function for isPlaying

  const ac_ref_speak = useRef(null); // AudioContext reference for speech synthesis
  const workLetRef_speak = useRef(null); // AudioWorkletNode reference for speech synthesis

  //const [asstResponding, setAsstResponding] = useState(true); // tracker for assistant response
  //const handleSetAsstResponding = (status) => setAsstResponding(status);

  const [panel, setPanel] = useState('text'); // initialize with text panel
  const handleSetPanel = (panel) => setPanel(panel); // parent setter function set panel

  const [tour_itinerary, setTour_itinerary] = useState(''); // initialize tour section
  const handleSetTour_itinerary = (text) => {console.log(tour_itinerary); setTour_itinerary(text)}; // parent setter function set tour guide text
  //#endregion

  //#region helper function
  useEffect(() => {
    (async () => { //connect to the server and fetch introduction audio
      try {
        await connectToServer({ // connect to the server and pass setter functions to server_functions module
          panel, handleSetPanel,
        //  caption,
        //  question_trans,
        //  setIntroAudio, isStartedRef,
        //  handleSetLoading, 
         // handleSetQuestion_trans,
        //  handleSetCaption, 
          handleSetTour_itinerary,
          setAudioQueue,
          //handleSetAsstResponding,
          audioQueue, isPlaying, setIsPlaying, currentAudio, setCurrentAudio
        });

        handleSetLoading(false); // Set to loading = false / loading complete after connecting to server
      } catch (error) {
        console.error("Error connecting to the server:", error);
      }
    })
    (); // Immediately invokes the async function
  }, []);

  const handleStartClick = () => { // when user clicks start button
    handleSetStart(true); //start the application
    makeServerRequest('introduction'); // request introduction from server
    setPanel('text'); //set the panel to text to show intro caption too
    if (!ac_ref_speak.current) {
      const ac = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
      ac_ref_speak.current = ac;
    }
    ac_ref_speak.current.resume();  // unlock context on user gesture
  };
  //#endregion 
  
  //#region server requests
  /*const reqProcessAudio = (blob) => {
    setPanel('text')
    makeServerRequest('question', blob)
  };*/

  const reqSendChunksToServer = (chunk) => {
    makeServerRequest('chunk', chunk);
  }

  const reqNotifyPlaybackComplete = () => {
    makeServerRequest('playback_complete', null);
  }

  const reqStopRun = () => {
    makeServerRequest('cancel', null);
  };
  //#endregion

  //#region navigator
  const Stack = createStackNavigator(); // stack navigator for start screen and main application
  const AppStackNav = () => (
    <Stack.Navigator>
      {!start ? 
      <Stack.Screen 
        name="StartScreen" 
        options={{ headerShown: false }} // Hide header
      >
        {props => <StartScreen {...props} loading={loading} handleStartClick={handleStartClick} />}
      </Stack.Screen> 
      : 
      <Stack.Screen 
      name="MainApp" 
      options={{ headerShown: false }} // Hide header
    >
      {props => (
        <MainApp 
          {...props}
          //#region mainappheader props
          start={start}
        //intro_audio={intro_audio}
        //setIntroAudio={setIntroAudio}
        //asstResponding={asstResponding}
          //
          recording={recording}
          handleSetRecording={handleSetRecording}
          recordingRef={recordingRef}
          ac_ref_listen={ac_ref_listen}
          workletNodeRef_listen={workletNodeRef_listen}
          sourceRef={sourceRef}
          accumulatedRef={accumulatedRef}
          streamRef={streamRef}
          //
          //reqProcessAudio={reqProcessAudio}
          reqSendChunksToServer={reqSendChunksToServer}
          audioQueue={audioQueue}
          setIsPlaying={setIsPlaying}
          //handleSetAsstResponding={handleSetAsstResponding}
          isPlaying={isPlaying}
          reqNotifyPlaybackComplete={reqNotifyPlaybackComplete}
          ac_ref_speak={ac_ref_speak}
          workLetRef_speak={workLetRef_speak}
          //
          currentAudio={currentAudio}
          setCurrentAudio={setCurrentAudio}
          reqStopRun={reqStopRun}
          //#endregion

          //#region mainapptextpanel props
          panel={panel}
          //question_trans = {question_trans}
          //caption={caption}
          tour_itinerary={tour_itinerary}
          handleSetPanel={handleSetPanel}
          //#endregion
        />
      )}
      </Stack.Screen>
      }
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
