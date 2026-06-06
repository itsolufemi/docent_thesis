import React from "react";
import { View } from 'react-native';
import Recorder from '../Recorder';
import AudioPlayer from '../AudioPlayer';
import { styles } from '../styles/styles';

export default function MainAppHeader({asstResponding, reqProcessAudio, audioQueue, setIsPlaying, handleSetAsstResponding, isPlaying, currentAudio, setCurrentAudio, reqStopRun}){ // main application header component{
    return (
        <View style={styles.section && styles.player}>
            {!asstResponding ? (
            <Recorder reqProcessAudio={reqProcessAudio} />
            ) : (
            <AudioPlayer
                audioQueue={audioQueue}
                setIsPlaying={setIsPlaying}
                handleSetAsstResponding={handleSetAsstResponding}
                isPlaying={isPlaying}
                currentAudio = {currentAudio}
                setCurrentAudio={setCurrentAudio}
                reqStopRun={reqStopRun}
            />
            )}
        </View>
    );
}