//App v.
/*UPDATE NOTES

*/

// #region imports and setup
require('dotenv').config();
const express = require('express');
const fileUpload = require('express-fileupload');
const AWS = require('aws-sdk');
const fs = require('fs');
const path = require('path');
const axios = require('axios');
const FormData = require('form-data');
const { OpenAI } = require('openai');
const openai = new OpenAI(process.env.OPENAI_API_KEY);
const cors = require('cors');
const app = express();
const speech = require('@google-cloud/speech'); // google cloud peech-to-Text
const { runInNewContext } = require('vm');
const client = new speech.SpeechClient(); // creating a speech-to-Text client


app.use(cors());
app.use(fileUpload({
  limits: { fileSize: 25 * 1024 * 1024 }, // 50 MB file size limit
}));
app.use(express.json({ limit: '10mb' })); // 10 MB JSON body limit
app.use(express.urlencoded({ extended: true, limit: '10mb' })); // For URL-encoded bodies


const port = process.env.PORT || 5000;
// #endregion

//#region assistant's global variables
let assistant = null; // retrieved assistant
let threadId = null; //threadId 
let runId = null; // Store the current run ID
let currentStream = null; // Store the current stream object
async function create_thread_and_assistant() { //create the assistant and thread at the beginning of the server run
  assistant = await openai.beta.assistants.retrieve("asst_e3phU73yAZIBbIdsmuRYsCHS"); //Retrieve the assistant at the top
  const thread = await openai.beta.threads.create(); //create overall thread
  threadId = thread.id; //set the threadId
  console.log(threadId);
}

create_thread_and_assistant();
//#endregion

const s3 = new AWS.S3({ // Configure AWS SDK
  accessKeyId: process.env.AWS_ACCESS_KEY_ID,
  secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
  region: process.env.AWS_REGION
});

// Endpoint to handle user welcome message
app.post('/introduction', async (req, res) => {
  try { //introductory message
    await openai.beta.threads.messages.create(threadId, {
      role: 'user',
      content: "welcome the user to the gallery, ask if there is anything in partiular they want to see, inform them that its fine if they dont know, thats why you're here to help, if they want to you put together a small tour for them or, they can walk around see if anything catches their eye and you'll get started there"
      //this to be generated later
    });

    const run = await openai.beta.threads.runs.createAndPoll( //create a new run
      threadId,{ assistant_id: assistant.id
    });

    let intro = '';
    if (run.status === 'completed') {//load the last response in the thread
      const messages = await openai.beta.threads.messages.list(run.thread_id);
      const lastMessage = messages.data.find(message => message.role === 'assistant');
      intro = lastMessage.content[0].text.value;
    } else {
      return 'Assistant welcome message not completed';
    }

    console.log('message:', intro);

    if (intro.length > 0) {//pass the entire response to the TTS endpoint
      const speech_url = await generateTTS(intro);
      res.json({
        type: 'audio',
        text: intro,
        value: speech_url, // S3 URL returned from generateTTS
      });
    } else {// handles empty response
      console.log('intro provided an empty response.');
      res.json({ type: 'text', text: 'no intro available' });
    }
  } catch (error) {
    console.error('Error with introduction:', error.response?.data || error.message);
    res.status(500).send('Error with introduction');
  }
});

// Endpoint to handle base64 audio upload and transcription with google api
app.post('/upload-base64', async (req, res) => {
  isCancelled = false; // Reset the cancellation flag

  const { audio, type } = req.body; // Extract base64 string and MIME type
  if (!audio || !type) {
    return res.status(400).json({ message: 'No audio data provided.' });
  }
  try {
    const buffer = Buffer.from(audio, 'base64'); // decode the base64 string
    const tempFilePath = path.join(__dirname, './public/audio.wav');  //where the audio will be saved
    fs.writeFileSync(tempFilePath, buffer); // save the audio file temporarily
    // Read the audio file into memory as base64
    const audioBytes = fs.readFileSync(tempFilePath).toString('base64');

    const request = {//configure the request
      audio: { content: audioBytes },
      config: {
        encoding: 'LINEAR16', // PCM encoding for .wav //remove for web
        sampleRateHertz: 16000, // Make sure it matches your recording sample rate //remove for web
        languageCode: 'en-US',
      },
    };

    // Perform Speech-to-Text request
    const [response] = await client.recognize(request);
    const transcriptionText = response.results.map(result => result.alternatives[0].transcript).join('\n');
    
    console.log('Transcription Text:', transcriptionText);

    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Transfer-Encoding', 'chunked');

    // use the transcription as the question for the assistant
    await getAssistantResponse(transcriptionText, res);
  } catch (error) {
    console.error('Error during base64 transcription:', error.message);
    res.status(500).json({ message: 'Error processing base64 audio' });
  }
});

// Endpoint to handle audio file upload and transcription with OpenAI's Whisper API
app.post('/upload', async (req, res) => {
    isCancelled = false; //reset the cancellation flag
  
    if (!req.files || !req.files.audio) {
      console.log('No files were uploaded.'); // Debugging line
      return res.status(400).json({ message: 'No files were uploaded.' });
    }
  
    const file = req.files.audio; // Ensure the key matches the client-side
  
    const uploadParams = {
      Bucket: process.env.S3_BUCKET_NAME,
      Key: 'audio.wav',
      Body: file.data
    };
  
    try {
      await s3.upload(uploadParams).promise(); // Upload the file to S3
  
      // Save the file locally to a temporary path
      const tempFilePath = path.join(__dirname, '/public/audios/temp_audio.wav');
      fs.writeFileSync(tempFilePath, file.data);
  
      // Transcribe the audio using OpenAI's Whisper API
      const formData = new FormData();
      formData.append('file', fs.createReadStream(tempFilePath));
      formData.append('model', 'whisper-1');
  
      const transcriptionResponse = await axios.post('https://api.openai.com/v1/audio/transcriptions', formData, {
        headers: {
          ...formData.getHeaders(),
          Authorization: `Bearer ${process.env.OPENAI_API_KEY}`
        }
      });
  
      const transcriptionText = transcriptionResponse.data.text;
      console.log('Transcription Text:', transcriptionText);
  
      // Get assistant response and handle streaming
      res.setHeader('Content-Type', 'application/json');
      res.setHeader('Transfer-Encoding', 'chunked');
  
      await getAssistantResponse(transcriptionText, res);
  
    } catch (error) {
      console.error('Error during transcription:', error.response?.data || error.message);
      res.status(500).send('Error processing audio');
    }
});

// Endpoint to handle run cancellation
let isCancelled = false; //its not cancelled until it is cancelled... lol
app.post('/cancel-run', async (req, res) => {
  isCancelled = true; // Set the cancellation flag
  if (currentStream) {
    currentStream = null; // Nullify current stream
  }

  try {
    const runStatusResponse = await openai.beta.threads.runs.retrieve(threadId, runId);
    const runStatus = runStatusResponse.status;

    if (runStatus === 'completed') { //if run is already completed
      console.log('Run already completed');
      res.status(200).json({ message: 'Run already completed' });
    } else{
      const cancelResponse = await openai.beta.threads.runs.cancel(threadId, runId);
      console.log('Run aborted: ', cancelResponse.status);
      res.status(200).json({ message: 'Run aborted', status: cancelResponse.status });
    }
  } catch (error) {
    console.error('Error cancelling run:', error);
    res.status(500).json({ message: 'Error cancelling run', error: error.message });
  }finally {// Clean up in aisle 3
    runId = null;
  }
});


// Endpoint to curate a tour
app.post('/tour', async (req, res) => {
  try { // ask the assistant to curate a tour
    await openai.beta.threads.messages.create(threadId, {
      role: "user",
      content: "explain to the user that you've prepared a tour of paintings in the gallery's highlight collection. return a list of paintings with the corresponding room number for each painting, using only sequence transition words to list the paintings instead of a numbered list. Ask the user to proceed to the appropriate room of the first painting to begin the tour. Remind the user that they can ask for directions to rooms from the staff around the gallery and ask the user to let you know when they are ready to begin"
    });

    const run = await openai.beta.threads.runs.createAndPoll( //create a new run
      threadId,{ assistant_id: assistant.id
    });

    let curated_tour = '';
    if (run.status === 'completed') {//load the last response in the thread
      const messages = await openai.beta.threads.messages.list(run.thread_id);
      const lastMessage = messages.data.find(message => message.role === 'assistant');
      curated_tour = lastMessage.content[0].text.value;
    } else {
      return 'Assistant response for tour not completed';
    }

    console.log('curated tour:', curated_tour);

    if (curated_tour.length > 0) {//pass the entire response to the TTS endpoint
      const speech_url = await generateTTS(curated_tour);
      res.json({
        type: 'audio',
        text: curated_tour,
        value: speech_url, // S3 URL returned from generateTTS
      });
    } else {// handles empty response
      console.log('curator provided an empty response.');
      res.json({ type: 'text', text: 'The curator did not provide a response.' });
    }
  } catch (error) {
    console.error('Error interacting with curator:', error.response?.data || error.message);
    res.status(500).send('Error interacting with curator');
  }
});

// Function to interact with the Assistant
const getAssistantResponse = async (inputText, res) => {
    try {// Create the message in the existing thread
      await openai.beta.threads.messages.create(threadId, {
        role: "user",
        content: inputText
      });
  
      // Create and stream the run response
      const stream = await openai.beta.threads.runs.create(threadId, {
        assistant_id: assistant.id,
        stream: true
      });
  
      // Store the current stream object
      currentStream = stream;
  
      let assistantResponse = '';
      let buffer = '';
      
      // Send the transcription text to the client first
      res.write(JSON.stringify({ type: 'transcription', value: inputText }) + '\n');
  
      for await (const event of stream) {
        if (isCancelled) { // Check for cancellation
          console.log('Stream cancelled by user');
          res.write(JSON.stringify({ type: 'cancelled' }) + '\n');
          res.end();
          isCancelled = false; // Reset the cancellation flag
          break;
        }
  
        if (event.event === 'thread.run.created') {
          runId = event.data.id;
        }
  
        if (event.event === 'thread.message.delta') {
          const contentArray = event.data.delta.content;
          if (Array.isArray(contentArray)) {
            buffer += contentArray.map(item => item.text.value).join('');
          }
  
          if (buffer.includes('\n\n')) {
            // Call TTS endpoint with the current chunk
            const speechurl = await generateTTS(buffer); //call the audio tts endpoint
            assistantResponse += buffer;
            process.stdout.write(buffer);
            res.write(JSON.stringify({  type: 'audio', text: buffer, value: speechurl }) + '\n');
            buffer = '';
          }
        }
  
        if (event.event === 'thread.run.completed') {
          if (buffer) {// Call TTS endpoint with the end chunk
            const speechurl = await generateTTS(buffer); //call the audio tts endpoint
            assistantResponse += buffer;
            process.stdout.write(buffer);
            res.write(JSON.stringify({type: 'audio', text: buffer, value: speechurl }) + '\n');
          }
          res.end();
          currentStream = null;
          break;
        }
      }
    } catch (error) {
      console.error('Error interacting with Assistant:', error.response?.data || error.message);
      res.status(500).send('Error interacting with Assistant');
      res.write(JSON.stringify({ type: 'cancelled' }) + '\n');
    }
};

// Endpoint to handle TTS requests
const generateTTS = async (text) => {
try {
    const response = await openai.audio.speech.create({
    model: "tts-1",
    voice: "nova",
    input: text
    });
    const bufferData = Buffer.from(await response.arrayBuffer());
    const speechFile = `speech_${Date.now()}.mp3`;
    
const uploadParams = { // upload parameters for S3
    Bucket: process.env.S3_BUCKET_NAME, // Your S3 bucket name
    Key: speechFile, // File name to save as in S3
    Body: bufferData,
    ContentType: 'audio/mpeg'
};   

await s3.upload(uploadParams).promise();

// Generate a signed URL
const signedUrlParams = {
    Bucket: process.env.S3_BUCKET_NAME,
    Key: speechFile,
    Expires: 86400 // 24 hours
};
const signedUrl = s3.getSignedUrl('getObject', signedUrlParams);

if(isCancelled) {
    console.log('no tts generated: cancelled');
    return null;
} else {  
console.log(`File uploaded successfully. Access it here for the next 24 hours: ${signedUrl}`);
return signedUrl;
}
} catch (error) {
    console.error('Error generating TTS:', error);
    throw new Error('Error generating TTS');
}
};

// Endpoint to handle app close
app.post('/close', async (req, res) => {
  console.log('closing app ...');
  try {
    const response = await openai.beta.threads.del(threadId);
    threadId = null; //reset the threadId
    console.log(response);
    await create_thread_and_assistant(); // wait to retrive the assistand and create new thread
    res.status(200).send('app closed'); //reponsd to the client after all is done
  } catch (error) {
    console.error('Error closing app:', error);
    res.status(500).send('Error closing app');
  }
});

// Start the server
app.listen(port, () => {
  console.log(`Server is running on http://localhost:${port}`);
});