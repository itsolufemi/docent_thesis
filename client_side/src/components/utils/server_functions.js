import { ipv4 } from './ipv4_module'; // Import ipv4 module to get the local ip address
const server = `ws://${ipv4}:8080`; // use the local ip address to connect to the server
//console.log('1. server address:', server); // Log the server address
let server_ws = null; // WebSocket client variable
let setters = null;
let shouldResetCaption = false; // Flag to indicate if the caption should be reset
let audioFunctions = {} // to hold audio functions from the audio player component
let captionFunctions = {} // to hold caption functions from the text panel component

//#region utility functions
const setAudioFunctionsinServer = (functions) => { // function to set the audio functions in the server
    audioFunctions = functions; // set the audio functions in the server   
};

const setCaptionFunctionsinServer = (functions) => { // function to set the caption functions in the server
    captionFunctions = functions; // set the caption functions in the server
};

const sendtoServer = (type, message) => {
    if(!server_ws) {
        console.error('WebSocket client not connected');
        return;
    }

    try {
      if (type === 'chunk' && message && (message.buffer || message.byteLength !== undefined)) {
        // message is a Uint8Array / ArrayBufferView → send as BINARY
        server_ws.send(message);
      } else {
        // control messages stay JSON
        const data = { type, payload: message };
        server_ws.send(JSON.stringify(data));
      }
    } catch (error) {
      console.log('Error sending to server:', error);
    }
};

const cancel_res = () => {
    console.log('stop response');
    //setters.handleSetAsstResponding(false); // set assistant responding to false
    setters.setAudioQueue([]); // clear the audio queue
    //captionFunctions.handleSetCaption(''); // reset the caption
    audioFunctions.stopAudio?.(); // stop legacy audio if configured
    sendtoServer('cancel', {}); // Send cancel request to server
}

//#endregion

const connectToServer = (import_setters) => { // 1. connection to server and handling incoming server messages (server --> cient)
    setters = import_setters;

    return new Promise((resolve, reject) => {
        if (server_ws) {
            server_ws.close(); // Close the existing connection if it exists
        }

        server_ws = new WebSocket(server); // Create a new WebSocket connection
        server_ws.binaryType = 'arraybuffer';

        server_ws.onopen = () => {
            console.log('Connected to server');
            resolve(); // Resolve the promise when connected
        };

        server_ws.onmessage = (event) => {
            if (typeof event.data !== 'string') {// handling incoming binary audio data from server (responses' pcm chunks)
                console.log('aud chunk')
                const buf = event.data; // arrayBuffer
                const pcm16 = new Int16Array(buf.slice(0)); // safe copy
                if (audioFunctions.enqueuePCM) { // enqueue the pcm16 chunk to the audio player
                    audioFunctions.enqueuePCM(pcm16); 
                }
                return;
            }

            const { type, payload } = JSON.parse(event.data); // handling predefined incoming json messages from server (control messages)
            switch (type) {
                case 'intro_ready':
                    console.log('recieved introduction audio');
                    /*
                    setters.setIntroAudio(payload.base64Wav); // Set the introduction audio URL
                    setters.Caption(payload.textBuffer); // Set the caption with the introduction text
                    setters.handleSetLoading(false); // Set loading to false  */
                    break;

                case 'question_transcript':
                    captionFunctions.handleSetQuestion_trans(payload.transcript); // set the question transcript
                    break;

                case 'response_transcript':  
                    if (shouldResetCaption) { // new response
                        shouldResetCaption = false; // deactivate the caption gate to  append next text chunks
                        captionFunctions.handleSetCaption(payload.transcript); // set the caption with the new text
                    } else { // ongoing response
                        captionFunctions.handleSetCaption((prev) => prev + payload.transcript); // append to the caption
                    }
                    break; 
                
                case 'audio_stream_complete': // server message indicating that all audio chunks have been streamed to client
                    console.log('server message: audio stream complete');
                    audioFunctions.msg_audioStreamComplete?.(); // notify legacy audio if configured
                    break;
                
                case 'reset_caption': // server indicates to reset the caption for new response
                    shouldResetCaption = true; // set the flag to reset the caption
                    console.log('caption will be reset for next response');
                    break;

                case 'tour_itinerary': // itenerary for requested tour, lists the artworks to be covered in the tour
                    setters.handleSetTour_itinerary(payload.itinerary);
                    console.log('itinerary recieved', /*payload.itinerary*/);
                    break;

                case 'cancel_res': //message from the server to halt asst response, needs to be sent here so that the frontend stops.
                    cancel_res();
                    break;
                
                default:
                    console.log('Unknown message type:', type, payload); // Handle unknown message types
                    break;
            }
        };

        server_ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            reject(error); // Reject the promise on error
        };

        server_ws.onclose = () => {
            console.log('Disconnected from server');
        };
    });
}

const makeServerRequest = async (type, payload = null,) => { // 2. handle different outgoing server requests (client --> server)
    if(type !== 'chunk'){
        setters.setAudioQueue([]); // Clear the audio queue
        shouldResetCaption = true; // Set the flag to reset the caption
    }

    switch (type) {
        case 'introduction':
            sendtoServer('introduction', null); // Send request to server for introduction
            break;

        case 'chunk':
            sendtoServer('chunk', payload); // Send audio chunk to server
            break;    

        case 'question': 
            setters.setAudioQueue([]); // reset the audio queue
            //setters.handleSetAsstResponding(true); // Set assistant responding to true
            //#region reader function to convert blob to base64 and upload to server
            const reader = new FileReader(); // Initialize FileReader to convert blob to base64
            reader.onloadend = async () => {
                try {
                    const base64data = reader.result.split(',')[1]; // extract the base64 string for the audio(blob) but exclude the prefix "data:audio/...;base64,"
                    const str_64AudioData = JSON.stringify({ //store the base64 audio data and audio type in an object and then strigify it, save to variable
                        audio: base64data, // The base64 audio data
                        type: payload.type, // Keep the audio type (e.g., "audio/wav" or "audio/webm")
                    });

                    try {
                        const upload = await fetch(`http://${ipv4}:5000/upload-audio`, { // upload the audio file to the server
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: str_64AudioData, // Send the base64 audio data to the server
                        }); 
                        
                        if(!upload.ok) {
                            throw new Error('file could not be saved')
                        }
                        sendtoServer('question', {}); // Send request to server for question 
                    }catch (error) {
                        console.error('error uploading file to public/:', error);
                        return;  
                    }
                }catch (error) {
                    console.error('error processing question', error);
                    return;
                }
            };
            //#endregion 
            reader.readAsDataURL(payload); // call function to convert blob to base64 and upload question to server
            break;

        case 'playback_complete':
            console.log('client side audio playback is complete');
            sendtoServer('playback_complete', {}); // notify the server that the client side audio playback is complete so that it can update its state accordingly
            break;

        case 'cancel':
            cancel_res()
            break;
        default:
            console.log('Unknown request type:', type); // Handle unknown request types
            break;
    }
}

export { connectToServer, makeServerRequest, setAudioFunctionsinServer, setCaptionFunctionsinServer };
