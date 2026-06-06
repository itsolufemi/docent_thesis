//tapscreen
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView } from 'react-native';
import Recorder from './Recorder';
import AudioPlayer from './AudioPlayer';
import { setCaptionFunctionsinServer } from "./utils/server_functions";
import { styles } from './styles/styles';

export default function MainApp(
    {start, intro_audio, setIntroAudio, 
    recording, handleSetRecording, recordingRef, ac_ref_listen, workletNodeRef_listen, sourceRef, accumulatedRef, streamRef, asstResponding, 
    reqSendChunksToServer, reqProcessAudio, 
    audioQueue, setIsPlaying, handleSetAsstResponding, isPlaying, currentAudio, setCurrentAudio, 
    ac_ref_speak, workLetRef_speak,
    reqNotifyPlaybackComplete, reqStopRun, 
    panel, 
    //question_trans, 
    //caption, 
    tour_itinerary, handleSetPanel}
){ // main application component

    const Header = () => ( // header with recorder and audio player 
        <View style={styles.section && styles.player}>
            <Recorder
                recording={recording}
                handleSetRecording={handleSetRecording}
                recordingRef={recordingRef}
                ac_ref_listen={ac_ref_listen}
                workletNodeRef_listen={workletNodeRef_listen}
                sourceRef={sourceRef}
                accumulatedRef={accumulatedRef}
                streamRef={streamRef}
                reqSendChunksToServer={reqSendChunksToServer}
                //reqProcessAudio={reqProcessAudio} 
                //disabled={asstResponding} // add a disabled prop
            />
            <AudioPlayer
                start={start}
                intro_audio={intro_audio}
                setIntroAudio={setIntroAudio}
                audioQueue={audioQueue}
                setIsPlaying={setIsPlaying}
                //handleSetAsstResponding={handleSetAsstResponding}
                isPlaying={isPlaying}
                //
                ac_ref_speak={ac_ref_speak}
                workLetRef_speak={workLetRef_speak}
                //
                currentAudio = {currentAudio}
                setCurrentAudio={setCurrentAudio}
                reqStopRun={reqStopRun}
                reqNotifyPlaybackComplete={reqNotifyPlaybackComplete}
            />
        </View>
    );

    const Body = () => { // nested text panel component
        const [question_trans, setQuestion_trans] = useState(''); //user question transcript
        const handleSetQuestion_trans = (transcript) => setQuestion_trans(transcript);

        const [caption, setCaption] = useState(''); // caption panel useState, sent here to prevent re-rendering other components in the main app particularly audio player
        const handleSetCaption = (text) => setCaption(text); // parent setter function set caption text

        setCaptionFunctionsinServer({ handleSetCaption, handleSetQuestion_trans }); // send caption setter function to server functions module
        return (
            <ScrollView style={[styles.scrollViewMain]}>
                    <Text style = {styles.questionBox}>{panel === 'text' ? question_trans : 'Tour Itenerary'}</Text>
                    <Text style={styles.textPanel}>{panel === 'text' ? caption : tour_itinerary}</Text>
            </ScrollView>
        );
    };


    return (
        <View style={styles.main}>
            <Header />
            <Body />
            <View style={styles.navigation}>
                <TouchableOpacity onPress={() => handleSetPanel('tour')} 
                style={[styles.navButton, !tour_itinerary && styles.disabledButton]} 
                disabled ={!tour_itinerary}>
                    <Text style={styles.icon}>Tour</Text>
                </TouchableOpacity>
                <TouchableOpacity 
                style={[styles.navButton, styles.disabledButton]} 
                disabled ={true}>
                    <Text style={styles.icon}>📷</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => handleSetPanel('text')} 
                style={styles.navButton}>
                    <Text style={styles.icon}>CC</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.closeButton}>
                    <Text style={styles.icon}>X</Text>
                </TouchableOpacity>
            </View>
        </View>
    );
};