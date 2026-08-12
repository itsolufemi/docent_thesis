class TtsPcmPlayerProcessor
  extends AudioWorkletProcessor {
  constructor() {
    super();

    this.queue = [];
    this.currentChunk = null;
    this.currentOffset = 0;

    this.queuedSamples = 0;
    this.prebufferSamples =
      Math.round(sampleRate * 0.12);

    this.streamComplete = false;
    this.playbackStarted = false;
    this.paused = false;
    this.underrunActive = false;
    this.underrunCount = 0;

    this.port.onmessage = (event) => {
      const message = event.data;

      if (message?.type === 'configure') {
        const prebufferMs = Number(
          message.prebufferMs,
        );

        if (
          Number.isFinite(prebufferMs) &&
          prebufferMs >= 0
        ) {
          this.prebufferSamples =
            Math.round(
              sampleRate *
              prebufferMs /
              1000,
            );
        }

        return;
      }

      if (message?.type === 'enqueue') {
        const samples = message.samples;

        if (
          samples instanceof Float32Array &&
          samples.length > 0
        ) {
          this.queue.push(samples);
          this.queuedSamples +=
            samples.length;

          this.underrunActive = false;
        }

        return;
      }

      if (message?.type === 'complete') {
        this.streamComplete = true;
        return;
      }

      if (message?.type === 'pause') {
        this.paused = true;

        this.port.postMessage({
          type: 'playback_paused',
        });

        return;
      }

      if (message?.type === 'resume') {
        this.paused = false;

        this.port.postMessage({
          type: 'playback_resumed',
        });

        return;
      }

      if (message?.type === 'flush') {
        this.reset();

        this.port.postMessage({
          type: 'playback_flushed',
        });
      }
    };
  }

  reset() {
    this.queue = [];
    this.currentChunk = null;
    this.currentOffset = 0;
    this.queuedSamples = 0;

    this.streamComplete = false;
    this.playbackStarted = false;
    this.paused = false;
    this.underrunActive = false;
    this.underrunCount = 0;
  }

  shouldBeginPlayback() {
    if (this.playbackStarted) {
      return true;
    }

    if (this.streamComplete) {
      return this.queuedSamples > 0;
    }

    return (
      this.queuedSamples >=
      this.prebufferSamples
    );
  }

  process(_inputs, outputs) {
    const outputChannel =
      outputs[0][0];

    outputChannel.fill(0);

    if (this.paused) {
      return true;
    }

    if (!this.shouldBeginPlayback()) {
      return true;
    }

    let outputOffset = 0;

    while (
      outputOffset <
      outputChannel.length
    ) {
      if (!this.currentChunk) {
        this.currentChunk =
          this.queue.shift() ?? null;

        this.currentOffset = 0;

        if (!this.currentChunk) {
          break;
        }

        if (!this.playbackStarted) {
          this.playbackStarted = true;

          this.port.postMessage({
            type: 'playback_started',
            bufferedSamples:
              this.queuedSamples,
            bufferedMilliseconds:
              (
                this.queuedSamples /
                sampleRate
              ) * 1000,
          });
        }
      }

      const remainingOutput =
        outputChannel.length -
        outputOffset;

      const remainingChunk =
        this.currentChunk.length -
        this.currentOffset;

      const copyLength = Math.min(
        remainingOutput,
        remainingChunk,
      );

      outputChannel.set(
        this.currentChunk.subarray(
          this.currentOffset,
          this.currentOffset +
            copyLength,
        ),
        outputOffset,
      );

      outputOffset += copyLength;
      this.currentOffset +=
        copyLength;

      this.queuedSamples = Math.max(
        0,
        this.queuedSamples -
          copyLength,
      );

      if (
        this.currentOffset >=
        this.currentChunk.length
      ) {
        this.currentChunk = null;
        this.currentOffset = 0;
      }
    }

    const queueEmpty = (
      !this.currentChunk &&
      this.queue.length === 0
    );

    if (
      this.playbackStarted &&
      queueEmpty &&
      !this.streamComplete &&
      !this.underrunActive
    ) {
      this.underrunActive = true;
      this.underrunCount += 1;

      this.port.postMessage({
        type: 'buffer_underrun',
        underrunCount:
          this.underrunCount,
      });
    }

    if (
      this.streamComplete &&
      queueEmpty
    ) {
      this.streamComplete = false;

      if (this.playbackStarted) {
        this.playbackStarted = false;

        this.port.postMessage({
          type: 'playback_complete',
          underrunCount:
            this.underrunCount,
        });
      }

      this.underrunActive = false;
      this.underrunCount = 0;
    }

    return true;
  }
}


registerProcessor(
  'tts-pcm-player',
  TtsPcmPlayerProcessor,
);
