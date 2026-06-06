# docent.ai (React + Node app in Expo scaffold/runtime)

A React app wrapped in an Expo scaffold/runtime that serves as a conversational museum docent experience. The app connects to a local backend WebSocket server, records user audio, streams audio chunks for processing, receives generated text and PCM audio responses, and plays back the guided narration in real time.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Key App Functions](#key-app-functions)
- [Component Breakdown](#component-breakdown)
- [Data Flow](#data-flow)
- [Important Files & Directories](#important-files--directories)
- [Setup and Running](#setup-and-running)
- [Notes and Considerations](#notes-and-considerations)
- [File Tree](#file-tree)

## Overview

`app--main` is the front-end of a React + Node app, encapsulated in an Expo scaffold/runtime. While Expo provides the app shell, build tools, and runtime environment, most of the actual app logic is implemented with plain React Native, browser Web APIs, and Node.js backend communication.

- uses Expo for cross-platform delivery and app shell/runtime setup
- captures microphone audio via Web Audio and AudioWorklet
- streams audio chunks to a local backend over WebSocket
- plays server-generated PCM audio through an AudioWorklet player
- presents live text captions and tour itinerary information
- uses a local `ipv4_module` to connect the app to the backend dynamically

> Note: The project is scaffolded within Expo, but the front-end behavior is mainly plain React Native and standard browser APIs. Expo is the wrapper/runtime, while audio capture, playback, and backend communication are handled by JavaScript and Web APIs rather than Expo-specific SDK features.

## Architecture

### High-level structure

- `App.js` - root component and app shell
- `index.js` - Expo entry point
- `components/` - UI and audio components
- `components/utils/` - communication and helper modules
- `backend/` - backend server, API and static assets
- `assets/` - static app assets
- `.expo/` - Expo runtime settings

### Runtime architecture

1. App starts via `index.js` and renders `App.js`
2. `App.js` loads `MainApplication`
3. `MainApplication` connects to the backend via `components/utils/server_functions.js`
4. `MainApplication` controls app navigation between `StartScreen` and `MainApp`
5. `MainApp` renders the recorder, audio player, caption panel, and tour controls
6. User audio is captured by `Recorder.js`, encoded, and sent to backend
7. Backend responds with text instructions and audio PCM chunks
8. `AudioPlayer.js` plays the streamed audio through a worklet engine

## Key App Functions

### `App.js`

- Root UI container
- Displays app title
- Renders `MainApplication`
- Uses `SafeAreaView` and `View`

### `MainApplication.js`

- Main app orchestration
- Creates app state and refs for loading, recording, audio queue, playback, tour panel, and navigation
- Connects to the backend using `connectToServer`
- Calls `makeServerRequest('introduction')` when the user starts
- Creates stack navigation between `StartScreen` and `MainApp`
- Passes server and audio control functions as props to child components

### `MainApp.js`

- App main screen after start
- Contains `Header` and `Body` sub-components
- `Header` includes `Recorder` and `AudioPlayer`
- `Body` displays text or tour itinerary
- Navigation buttons toggle the displayed panel and manage tour text
- Uses `setCaptionFunctionsinServer` to register caption handlers with the communication module

### `StartScreen.js`

- Simple launch screen
- Displays a start button
- Disables button while loading
- Calls `handleStartClick` to trigger backend introduction and app navigation

### `Recorder.js`

- Captures microphone input using Web Audio APIs
- Loads `recorder.worklet.js` from the backend static `public/worklets` directory
- Converts float stream audio to 16-bit PCM
- Sends PCM audio chunks to the backend over WebSocket via `reqSendChunksToServer`
- Manages recording lifecycle, cleanup, and audio context state

### `AudioPlayer.js`

- Loads `pcm-player.worklet.js` from backend static server
- Uses `AudioWorkletNode` for real-time PCM playback
- Handles playback completion and stop/cancel signals
- Exposes chime playback helpers for start/stop events

### `components/utils/server_functions.js`

- Manages front-end WebSocket connection to backend
- Sends JSON control messages and binary PCM chunks
- Handles incoming messages like:
  - `question_transcript`
  - `response_transcript`
  - `audio_stream_complete`
  - `tour_itinerary`
  - `cancel_res`
- Provides methods to enqueue audio, stop playback, and reset captions
- Uses `ipv4_module.js` to determine backend host address dynamically

## Data Flow

### Startup

- `MainApplication` uses `connectToServer()` to open a WebSocket to `ws://<ipv4>:8080`
- Backend writes the device IP into `components/utils/ipv4_module.js`
- Once connected, the app is ready to request introduction audio

### Recording flow

- User taps the record button in `Recorder`
- `Recorder` creates an `AudioContext` at 16kHz
- Loads `recorder.worklet.js` from backend `public/worklets`
- Microphone stream is captured and converted to PCM chunks
- Each PCM chunk is streamed over WebSocket as binary data via `server_functions.sendtoServer('chunk', ...)`

### Response flow

- Backend sends text updates via WebSocket JSON messages
- `server_functions` updates captions and tour itinerary via registered callbacks
- Backend sends binary PCM fragments for voice response
- `AudioPlayer` enqueues PCM chunks to its audio worklet
- When playback ends, the client notifies the backend with `playback_complete`

## Important Files & Directories

### Root

- `package.json` - app dependencies, expo scripts
- `App.js` - root component
- `index.js` - Expo entry point
- `app.json` - Expo app configuration
- `tsconfig.json` - TypeScript config

### Components

- `components/MainApplication.js` - app orchestration and navigation
- `components/MainApp.js` - main interactive screen
- `components/StartScreen.js` - start button view
- `components/Recorder.js` - microphone capture
- `components/AudioPlayer.js` - audio playback
- `components/LoginForm.js` - login screen placeholder
- `components/TicketForm.js` - ticket UI placeholder
- `components/utils/server_functions.js` - backend websocket communication
- `components/utils/ipv4_module.js` - auto-generated backend IP helper

### Backend

- `backend/server.js` - backend server, OpenAI realtime integration, routing, and static file serving
- `backend/server.expo.js` - alternate server entry for Expo or web context
- `backend/package.json` - backend dependencies
- `backend/public/` - static files served to frontend, including `worklets`
- `backend/db/` - local database or storage files
- `backend/.env` - environment variables (not committed)

## Setup and Running

### Requirements

- Node.js / npm
- Expo CLI or Expo Go
- Local network connectivity between front-end and backend
- Valid environment variables for backend OpenAI integration in `backend/.env`

### Front-end

From `app--main`:

```bash
cd c:\Users\itsol\Documents\docent-app\app--main
npm install
npm start
```

Or use Expo shortcuts:

```bash
npm run android
npm run ios
npm run web
```

### Backend

The backend runs separately from the Expo app. In `app--main/backend`:

```bash
cd c:\Users\itsol\Documents\docent-app\app--main\backend
npm install
node server.js
```

The backend serves:

- `http://<ipv4>:5000` static assets and audio worklets
- `ws://<ipv4>:8080` WebSocket for real-time communication

## Notes and Considerations

- `server.js` writes the local IPv4 address into `components/utils/ipv4_module.js`. This file is required by the front-end to connect to the backend.
- The frontend assumes the backend is reachable on the local network and serves the worklet files from `backend/public/worklets/`.
- Audio is captured at 16kHz and converted to 16-bit PCM.
- The app is structured for a voice-driven museum guide, although login and ticket screens are present as UI scaffolding.
- Expo is mainly used for app initialization, dependency management, and the runtime shell; most business logic and audio handling are implemented with standard React Native/Browsers APIs.
- Some features are currently commented out or stubbed, such as `LoginForm`, `TicketForm`, and extra caption handling.

## File Tree

```
app--main/
├─ App.js
├─ app.json
├─ index.js
├─ package.json
├─ package-lock.json
├─ tsconfig.json
├─ assets/
├─ components/
│  ├─ AudioPlayer.js
│  ├─ LoginForm.js
│  ├─ MainApp.js
│  ├─ MainApplication.js
│  ├─ Recorder.js
│  ├─ StartScreen.js
│  ├─ TicketForm.js
│  ├─ archive/
│  ├─ audio/
│  ├─ styles/
│  └─ utils/
│     ├─ server_functions.js
│     └─ ipv4_module.js
├─ backend/
│  ├─ .env
│  ├─ package.json
│  ├─ server.js
│  ├─ server.expo.js
│  ├─ db/
│  ├─ public/
│  │  ├─ chimes/
│  │  └─ worklets/
│  └─ response.wav
└─ .expo/
```

## Recommended Improvements

- Add a dedicated README in `backend/` describing backend startup and API details.
- Document expected `.env` variables and any OpenAI configuration.
- Add comments in `server_functions.js` for each message type and the backend message contract.
- Add a `README.md` for `components/utils` and clarify `ipv4_module.js` generation.
- Provide a more complete tour / artwork UI experience using a dedicated screen and buttons.
