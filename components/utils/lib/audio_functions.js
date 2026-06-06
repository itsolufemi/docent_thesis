
let curr_Audio = null; // global variable to store the current audio object

const queueAudio = (base64Wav, audioQueue, isPlaying, setIsPlaying, handleSetAsstResponding, setCurrentAudio) => {
    const aud_uri = `data:audio/wav;base64,${base64Wav}`; // store as a string representation of the audio
    audioQueue.current.push(aud_uri); // Add the audio to the queue
    /* if (audioQueue.current.length < 2) {
        return; 
        do not play audion until there are at least 4 audio chunks
        this is to prevent the audio from playing too fast in a bid to prevent
        latency between the audio chunks
        the method allows audio chunks to build up.
        
    }*/
    if (!isPlaying.current) {
        playNextAudio(audioQueue, setIsPlaying, handleSetAsstResponding,isPlaying, setCurrentAudio); // Play the audio if not already playing
    }
};

const playNextAudio = async (audioQueue, setIsPlaying, handleSetAsstResponding, isPlaying, setCurrentAudio) => {
    try{
    if (audioQueue.current.length === 0) {
        setIsPlaying(false);
        handleSetAsstResponding(false); // Set assistant responding to false when audio ends
        setCurrentAudio(null); // Reset current audio to null
        console.log()
        curr_Audio = null; // Reset current audio object
        return;
    }

    setIsPlaying(true); // audio is playing ? yes
    const uri = audioQueue.current.shift(); // set the first element in the array as the next audio to play 

/*    const { sound } = await Audio.Sound.createAsync(
        { uri },
        { shouldPlay: true }
    ); */

    setCurrentAudio(uri);
    curr_Audio = uri; // set the current audio object
    player.replace(uri); // replace the current audio with the new audio
    player.play(); // play the audio
    //sound.playAsync();

    sound.setOnPlaybackStatusUpdate((status) => {
        if (status.didJustFinish) {
            setIsPlaying(false);
            playNextAudio(audioQueue, setIsPlaying, handleSetAsstResponding, isPlaying, setCurrentAudio); // Play next audio when current audio ends
        };

        if (status.error) {
            console.error('Error playing audio');
            setIsPlaying(false);
            stopAudio(curr_Audio, setCurrentAudio, setIsPlaying); // Stop the audio if there is an error
        };
    });

    }catch(error) {
        console.log('Error: ', error);
    }
};

const stopAudio = (currentAudio, setCurrentAudio, setIsPlaying) => { //to stop the audio
    if (currentAudio.current) {
        currentAudio.current.stopAsync();
        console.log('3. audio stopped');
        setCurrentAudio(null);
        curr_Audio = null; // Reset current audio object
    }

    setIsPlaying(false);
    return;
};

export {queueAudio, playNextAudio, stopAudio};   