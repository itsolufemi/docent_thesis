"use client";

import JSZip from "jszip";
import { useEffect, useMemo, useRef, useState } from "react";
import { recordingPrompts, type RecordingPrompt, type TurnLabel } from "./prompts";

const TARGET_SAMPLE_RATE = 16_000;
const MAX_RECORDING_SECONDS = 10;
const DATABASE_NAME = "smart-turn-human-recordings";
const STORE_NAME = "recordings";

type StoredRecording = {
  id: string;
  blob: Blob;
  durationSeconds: number;
  recordedAt: string;
};

type Filter = "all" | "pending" | TurnLabel;

type DirectoryHandleLike = {
  getDirectoryHandle(
    name: string,
    options?: { create?: boolean },
  ): Promise<DirectoryHandleLike>;
  getFileHandle(
    name: string,
    options?: { create?: boolean },
  ): Promise<{
    createWritable(): Promise<{
      write(data: Blob | string): Promise<void>;
      close(): Promise<void>;
    }>;
  }>;
};

function openRecordingDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        request.result.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function loadStoredRecordings(): Promise<StoredRecording[]> {
  const database = await openRecordingDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readonly");
    const request = transaction.objectStore(STORE_NAME).getAll();
    request.onsuccess = () => resolve(request.result as StoredRecording[]);
    request.onerror = () => reject(request.error);
    transaction.oncomplete = () => database.close();
  });
}

async function persistRecording(recording: StoredRecording): Promise<void> {
  const database = await openRecordingDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).put(recording);
    transaction.oncomplete = () => {
      database.close();
      resolve();
    };
    transaction.onerror = () => reject(transaction.error);
  });
}

async function removeStoredRecording(id: string): Promise<void> {
  const database = await openRecordingDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).delete(id);
    transaction.oncomplete = () => {
      database.close();
      resolve();
    };
    transaction.onerror = () => reject(transaction.error);
  });
}

function flattenChunks(chunks: Float32Array[]): Float32Array {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const output = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.length;
  }
  return output;
}

function resampleAudio(
  samples: Float32Array,
  sourceSampleRate: number,
): Float32Array {
  if (sourceSampleRate === TARGET_SAMPLE_RATE) {
    return samples;
  }

  const ratio = sourceSampleRate / TARGET_SAMPLE_RATE;
  const outputLength = Math.max(1, Math.round(samples.length / ratio));
  const output = new Float32Array(outputLength);
  for (let index = 0; index < outputLength; index += 1) {
    const sourcePosition = index * ratio;
    const leftIndex = Math.floor(sourcePosition);
    const rightIndex = Math.min(leftIndex + 1, samples.length - 1);
    const fraction = sourcePosition - leftIndex;
    output[index] =
      samples[leftIndex] * (1 - fraction) + samples[rightIndex] * fraction;
  }
  return output;
}

function encodePcm16Wav(samples: Float32Array): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeText = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  };

  writeText(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, TARGET_SAMPLE_RATE, true);
  view.setUint32(28, TARGET_SAMPLE_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(
      offset,
      clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff,
      true,
    );
    offset += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

function csvValue(value: string | number): string {
  const stringValue = String(value);
  return /[",\n]/.test(stringValue)
    ? `"${stringValue.replaceAll('"', '""')}"`
    : stringValue;
}

function recordingFilename(prompt: RecordingPrompt): string {
  return `${prompt.id}.wav`;
}

function buildManifest(recordings: Map<string, StoredRecording>): string {
  const headers = [
    "case_id",
    "audio_path",
    "expected_label",
    "transcript",
    "category",
    "source",
    "voice",
    "delivery_note",
    "duration_seconds",
    "recorded_at",
  ];
  const rows = recordingPrompts
    .filter((prompt) => recordings.has(prompt.id))
    .map((prompt) => {
      const recording = recordings.get(prompt.id)!;
      return [
        prompt.id,
        `audio/human_suite/${recordingFilename(prompt)}`,
        prompt.label,
        prompt.text.replaceAll("—", ""),
        prompt.category,
        "human",
        "",
        prompt.delivery,
        recording.durationSeconds.toFixed(3),
        recording.recordedAt,
      ];
    });

  return [headers, ...rows]
    .map((row) => row.map(csvValue).join(","))
    .join("\n");
}

async function writeFile(
  directory: DirectoryHandleLike,
  name: string,
  data: Blob | string,
) {
  const fileHandle = await directory.getFileHandle(name, { create: true });
  const writable = await fileHandle.createWritable();
  await writable.write(data);
  await writable.close();
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

export function RecorderLab() {
  const [activeIndex, setActiveIndex] = useState(0);
  const [filter, setFilter] = useState<Filter>("all");
  const [recordings, setRecordings] = useState(
    () => new Map<string, StoredRecording>(),
  );
  const [recording, setRecording] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [message, setMessage] = useState("Choose a prompt and record naturally.");
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [outputFolderName, setOutputFolderName] = useState("");

  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const startedAtRef = useRef(0);
  const activeRecordingIdRef = useRef("");
  const timerRef = useRef<number | null>(null);
  const directoryRef = useRef<DirectoryHandleLike | null>(null);

  const activePrompt = recordingPrompts[activeIndex];
  const completedCount = recordings.size;
  const progress = (completedCount / recordingPrompts.length) * 100;
  const visiblePrompts = useMemo(
    () =>
      recordingPrompts.filter((prompt) => {
        if (filter === "pending") return !recordings.has(prompt.id);
        if (filter === "complete" || filter === "incomplete") {
          return prompt.label === filter;
        }
        return true;
      }),
    [filter, recordings],
  );

  useEffect(() => {
    loadStoredRecordings()
      .then((items) => {
        setRecordings(new Map(items.map((item) => [item.id, item])));
      })
      .catch(() => {
        setMessage("Saved recordings could not be restored in this browser.");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
      streamRef.current?.getTracks().forEach((track) => track.stop());
      void contextRef.current?.close();
    };
  }, []);

  const stopRecording = async () => {
    if (!recording || !contextRef.current) return;

    const context = contextRef.current;
    const sampleRate = context.sampleRate;
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if (processorRef.current) processorRef.current.onaudioprocess = null;
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }

    await context.close();
    const resampled = resampleAudio(flattenChunks(chunksRef.current), sampleRate);
    const blob = encodePcm16Wav(resampled);
    const durationSeconds = resampled.length / TARGET_SAMPLE_RATE;
    const promptId = activeRecordingIdRef.current;
    const stored: StoredRecording = {
      id: promptId,
      blob,
      durationSeconds,
      recordedAt: new Date().toISOString(),
    };

    await persistRecording(stored);
    const updated = new Map(recordings);
    updated.set(promptId, stored);
    setRecordings(updated);

    if (directoryRef.current) {
      const audioDirectory = await directoryRef.current
        .getDirectoryHandle("audio", { create: true })
        .then((directory) =>
          directory.getDirectoryHandle("human_suite", { create: true }),
        );
      const prompt = recordingPrompts.find((item) => item.id === promptId)!;
      await writeFile(audioDirectory, recordingFilename(prompt), blob);
    }

    streamRef.current = null;
    contextRef.current = null;
    processorRef.current = null;
    sourceRef.current = null;
    chunksRef.current = [];
    setRecording(false);
    setLevel(0);
    setElapsedSeconds(durationSeconds);
    setMessage(
      directoryRef.current
        ? "Recording accepted and written to the selected workspace."
        : "Recording accepted and saved in this browser.",
    );
  };

  useEffect(() => {
    if (recording && elapsedSeconds >= MAX_RECORDING_SECONDS) {
      void stopRecording();
    }
    // The recorder refs are intentionally authoritative during capture.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elapsedSeconds, recording]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
      const context = new AudioContext();
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);

      chunksRef.current = [];
      activeRecordingIdRef.current = activePrompt.id;
      startedAtRef.current = performance.now();
      streamRef.current = stream;
      contextRef.current = context;
      sourceRef.current = source;
      processorRef.current = processor;
      processor.onaudioprocess = (event) => {
        const samples = event.inputBuffer.getChannelData(0);
        chunksRef.current.push(new Float32Array(samples));
        let energy = 0;
        for (const sample of samples) energy += sample * sample;
        setLevel(Math.min(1, Math.sqrt(energy / samples.length) * 5));
      };

      source.connect(processor);
      processor.connect(context.destination);
      setElapsedSeconds(0);
      setRecording(true);
      setMessage("Recording… speak the prompt, then press stop.");
      timerRef.current = window.setInterval(() => {
        setElapsedSeconds((performance.now() - startedAtRef.current) / 1_000);
      }, 80);
    } catch (error) {
      console.error(error);
      setMessage(
        "Microphone access failed. Allow microphone permission for localhost and try again.",
      );
    }
  };

  const discardRecording = async (promptId: string) => {
    await removeStoredRecording(promptId);
    const updated = new Map(recordings);
    updated.delete(promptId);
    setRecordings(updated);
    setElapsedSeconds(0);
    setMessage("Recording removed. You can record this prompt again.");
  };

  const chooseOutputFolder = async () => {
    const picker = (
      window as Window & {
        showDirectoryPicker?: () => Promise<DirectoryHandleLike>;
      }
    ).showDirectoryPicker;
    if (!picker) {
      setMessage(
        "Direct folder writing is unavailable here. Use “Download benchmark ZIP” instead.",
      );
      return;
    }
    try {
      directoryRef.current = await picker();
      setOutputFolderName("Smart Turn workspace selected");
      setMessage("New recordings will also be written into audio/human_suite.");
    } catch {
      setMessage("Folder selection was cancelled.");
    }
  };

  const exportToFolder = async () => {
    if (!directoryRef.current) {
      await chooseOutputFolder();
      return;
    }

    setExporting(true);
    try {
      const audioDirectory = await directoryRef.current
        .getDirectoryHandle("audio", { create: true })
        .then((directory) =>
          directory.getDirectoryHandle("human_suite", { create: true }),
        );
      for (const prompt of recordingPrompts) {
        const stored = recordings.get(prompt.id);
        if (stored) {
          await writeFile(audioDirectory, recordingFilename(prompt), stored.blob);
        }
      }
      await writeFile(
        directoryRef.current,
        "smart_turn_human_manifest.csv",
        buildManifest(recordings),
      );
      setMessage(`Exported ${recordings.size} WAV files and the benchmark manifest.`);
    } finally {
      setExporting(false);
    }
  };

  const downloadBundle = async () => {
    setExporting(true);
    try {
      const zip = new JSZip();
      const audioFolder = zip.folder("audio/human_suite")!;
      for (const prompt of recordingPrompts) {
        const stored = recordings.get(prompt.id);
        if (stored) audioFolder.file(recordingFilename(prompt), stored.blob);
      }
      zip.file("smart_turn_human_manifest.csv", buildManifest(recordings));
      zip.file(
        "recording_notes.md",
        [
          "# Smart Turn human recording suite",
          "",
          `Exported: ${new Date().toISOString()}`,
          `Recordings: ${recordings.size} / ${recordingPrompts.length}`,
          "Format: 16 kHz mono PCM16 WAV",
          "",
          "Extract this bundle into ml_lab/smart_turn_workspace.",
        ].join("\n"),
      );
      const blob = await zip.generateAsync({
        type: "blob",
        compression: "DEFLATE",
        compressionOptions: { level: 6 },
      });
      downloadBlob(blob, "smart_turn_human_recordings.zip");
      setMessage(`Downloaded a bundle containing ${recordings.size} recordings.`);
    } finally {
      setExporting(false);
    }
  };

  const moveToPrompt = (prompt: RecordingPrompt) => {
    if (recording) return;
    setActiveIndex(prompt.order - 1);
    setElapsedSeconds(recordings.get(prompt.id)?.durationSeconds ?? 0);
    setMessage(
      recordings.has(prompt.id)
        ? "This prompt is complete. Replay it or record a replacement."
        : "Read the delivery note, then record the prompt.",
    );
  };

  const moveRelative = (offset: number) => {
    const nextIndex = Math.min(
      recordingPrompts.length - 1,
      Math.max(0, activeIndex + offset),
    );
    moveToPrompt(recordingPrompts[nextIndex]);
  };

  const currentRecording = recordings.get(activePrompt.id);
  const currentAudioUrl = useMemo(
    () => (currentRecording ? URL.createObjectURL(currentRecording.blob) : ""),
    [currentRecording],
  );

  useEffect(() => {
    return () => {
      if (currentAudioUrl) URL.revokeObjectURL(currentAudioUrl);
    };
  }, [currentAudioUrl]);

  return (
    <main className="lab-shell">
      <header className="lab-header">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">ST</span>
          <div>
            <p className="eyebrow">Docent · ML Lab</p>
            <h1>Human turn-recording study</h1>
          </div>
        </div>
        <div className="header-progress" aria-label={`${completedCount} of 40 complete`}>
          <span>{completedCount} / {recordingPrompts.length}</span>
          <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
          <small>{Math.round(progress)}% recorded</small>
        </div>
      </header>

      <section className="study-note">
        <div>
          <span className="note-index">01</span>
          <p>
            Record in your ordinary voice. For incomplete prompts, stop as if
            you genuinely intend to continue—never pronounce the ellipsis.
          </p>
        </div>
        <div>
          <span className="note-index">02</span>
          <p>
            Keep the same microphone distance and a quiet room. Replay anything
            clipped, unusually loud, or unlike your natural speech.
          </p>
        </div>
      </section>

      <div className="workspace-grid">
        <aside className="prompt-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">Recording script</p><h2>40 utterances</h2></div>
            <span className="saved-status">{loading ? "Loading…" : `${completedCount} saved`}</span>
          </div>
          <div className="filter-row" aria-label="Filter prompts">
            {(["all", "pending", "complete", "incomplete"] as Filter[]).map(
              (value) => (
                <button
                  key={value}
                  className={filter === value ? "is-active" : ""}
                  onClick={() => setFilter(value)}
                  type="button"
                >
                  {value}
                </button>
              ),
            )}
          </div>
          <ol className="prompt-list">
            {visiblePrompts.map((prompt) => {
              const isRecorded = recordings.has(prompt.id);
              return (
                <li key={prompt.id}>
                  <button
                    type="button"
                    onClick={() => moveToPrompt(prompt)}
                    className={prompt.id === activePrompt.id ? "is-current" : ""}
                    aria-current={prompt.id === activePrompt.id ? "step" : undefined}
                  >
                    <span className={`prompt-state ${isRecorded ? "is-recorded" : ""}`}>
                      {isRecorded ? "✓" : String(prompt.order).padStart(2, "0")}
                    </span>
                    <span className="prompt-list-copy">
                      <strong>{prompt.categoryLabel}</strong>
                      <small>{prompt.text}</small>
                    </span>
                    <span className={`label-dot ${prompt.label}`} title={prompt.label} />
                  </button>
                </li>
              );
            })}
          </ol>
        </aside>

        <section className="recording-stage">
          <div className="prompt-meta">
            <span>Prompt {String(activePrompt.order).padStart(2, "0")}</span>
            <span className={`label-pill ${activePrompt.label}`}>
              Expected {activePrompt.label}
            </span>
            <span>{activePrompt.categoryLabel}</span>
          </div>
          <blockquote>{activePrompt.text}</blockquote>
          <div className="delivery-card">
            <span>Delivery direction</span>
            <p>{activePrompt.delivery}</p>
          </div>

          <div className={`recorder-console ${recording ? "is-recording" : ""}`}>
            <div className="meter-zone">
              <div className="meter-bars" aria-label="Microphone level">
                {Array.from({ length: 24 }, (_, index) => (
                  <span
                    key={index}
                    className={index / 24 < level ? "is-live" : ""}
                    style={{ height: `${18 + ((index * 17) % 30)}px` }}
                  />
                ))}
              </div>
              <div className="time-readout">{elapsedSeconds.toFixed(1)}<span>s</span></div>
            </div>
            <div className="recording-actions">
              <button
                type="button"
                className={`record-button ${recording ? "is-stop" : ""}`}
                onClick={() => recording ? void stopRecording() : void startRecording()}
              >
                <span aria-hidden="true" />
                {recording
                  ? "Stop & accept"
                  : currentRecording
                    ? "Record again"
                    : "Start recording"}
              </button>
              {currentRecording && !recording && (
                <button
                  type="button"
                  className="quiet-button danger"
                  onClick={() => void discardRecording(activePrompt.id)}
                >
                  Discard
                </button>
              )}
            </div>
            {currentRecording && !recording && (
              <div className="playback-row">
                <span>Saved take · {currentRecording.durationSeconds.toFixed(2)}s</span>
                <audio controls src={currentAudioUrl} preload="metadata" />
              </div>
            )}
            <p className="recorder-message" aria-live="polite">{message}</p>
          </div>

          <div className="step-navigation">
            <button type="button" onClick={() => moveRelative(-1)} disabled={activeIndex === 0 || recording}>
              ← Previous
            </button>
            <span>{activePrompt.order} of {recordingPrompts.length}</span>
            <button
              type="button"
              onClick={() => moveRelative(1)}
              disabled={activeIndex === recordingPrompts.length - 1 || recording}
            >
              Next →
            </button>
          </div>
        </section>

        <aside className="export-panel">
          <div>
            <p className="eyebrow">Local storage</p>
            <h2>Benchmark assets</h2>
            <p className="export-copy">
              Recordings persist in this browser. Choose the Smart Turn
              workspace to also write WAV files directly into
              <code> audio/human_suite</code>.
            </p>
          </div>
          <button type="button" className="folder-button" onClick={chooseOutputFolder}>
            <span aria-hidden="true">⌑</span>
            {outputFolderName || "Choose Smart Turn workspace"}
          </button>
          <div className="export-stats">
            <div><strong>{recordings.size}</strong><span>WAV files ready</span></div>
            <div><strong>16 kHz</strong><span>Mono PCM16</span></div>
          </div>
          <button
            type="button"
            className="primary-export"
            onClick={() => void exportToFolder()}
            disabled={recordings.size === 0 || exporting}
          >
            Export to selected folder
          </button>
          <button
            type="button"
            className="secondary-export"
            onClick={() => void downloadBundle()}
            disabled={recordings.size === 0 || exporting}
          >
            Download benchmark ZIP
          </button>
          <div className="manifest-preview">
            <span>Manifest</span>
            <code>smart_turn_human_manifest.csv</code>
            <small>Compatible with benchmark_smart_turn.py</small>
          </div>
        </aside>
      </div>
    </main>
  );
}
