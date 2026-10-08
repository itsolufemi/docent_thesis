# Smart Turn Human Recording Lab

A local browser recorder for producing the 40-item human speech benchmark used
to evaluate Smart Turn on this machine.

## Start the recorder

From the repository root:

```powershell
cd ml_lab\smart_turn_workspace\recording_lab
npm.cmd run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Record the suite

1. Select **Choose Smart Turn workspace** and choose:
   `C:\Users\itsol\Documents\docent_thesis\ml_lab\smart_turn_workspace`
2. Work through all 40 prompts using your normal speaking style.
3. For incomplete prompts, stop naturally at the displayed boundary. Do not
   pronounce the ellipsis.
4. Replay each recording and use **Accept recording** when it is satisfactory.

Recordings are captured as 16 kHz mono PCM16 WAV files. When the workspace
folder is connected, the app writes them to:

```text
audio/human_suite/
```

It also creates:

```text
smart_turn_human_manifest.csv
```

Recordings are retained in the browser between reloads. If direct folder access
is unavailable, use **Download benchmark ZIP**, then extract its contents into
`ml_lab\smart_turn_workspace`.

## Run the CPU benchmark

From `ml_lab\smart_turn_workspace`:

```powershell
.\run_human_smart_turn_benchmark.ps1
```

The detailed JSON result is written to:

```text
results/smart_turn_human_results.json
```
