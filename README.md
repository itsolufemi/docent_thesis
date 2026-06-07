# docent.ai

A React + Node app for a conversational museum docent experience. The client is a plain React app under `client_side`, built with Vite, and the backend serves local APIs, static audio worklets, and WebSocket communication.

## Structure

- `client_side/` - React client app
- `client_side/src/` - client source files
- `client_side/src/components/` - UI, audio recording, audio playback, and app orchestration components
- `backend/` - Node/Express/WebSocket backend
- `backend/public/` - static worklets and chime assets served by the backend
- `assets/` - shared static assets

## Client

The client entry point is:

- `client_side/index.html`
- `client_side/src/main.jsx`
- `client_side/src/App.jsx`

The UI is standard React DOM: JSX elements, CSS classes, browser `fetch`, browser WebSocket, Web Audio, and AudioWorklet APIs.

## Backend Connection

On startup, `backend/server.js` detects the machine IPv4 address and writes it to:

```txt
client_side/src/components/utils/ipv4_module.js
```

The client imports that generated module to connect to:

- `http://<ipv4>:5000` for static worklets, chimes, and upload routes
- `ws://<ipv4>:8080` for real-time client/backend communication

## Running

Install client dependencies:

```sh
npm --prefix client_side install
```

Start the React client:

```sh
npm run dev
```

Start the backend separately from `backend/` according to the backend environment requirements.

## Notes

The former Expo/React Native scaffold has been removed. The root package delegates client commands to `client_side`, and the client package owns its own React/Vite dependencies.
