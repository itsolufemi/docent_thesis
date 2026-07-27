class TtsPcmPlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    this.queue = [];
    this.currentChunk = null;
    this.currentOffset = 0;
    this.streamComplete = false;
    this.playbackStarted = false;

    this.port.onmessage = (event) => {
      const message = event.data;

      if (message?.type === 'enqueue') {
        const samples = message.samples;

        if (
          samples instanceof Float32Array &&
          samples.length > 0
        ) {
          this.queue.push(samples);
        }

        return;
      }

      if (message?.type === 'complete') {
        this.streamComplete = true;
        return;
      }

      if (message?.type === 'flush') {
        this.queue = [];
        this.currentChunk = null;
        this.currentOffset = 0;
        this.streamComplete = false;
        this.playbackStarted = false;

        this.port.postMessage({
          type: 'playback_flushed',
        });
      }
    };
  }

  process(_inputs, outputs) {
    const output = outputs[0];
    const outputChannel = output[0];

    outputChannel.fill(0);

    let outputOffset = 0;

    while (
      outputOffset < outputChannel.length
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
      this.currentOffset += copyLength;

      if (
        this.currentOffset >=
        this.currentChunk.length
      ) {
        this.currentChunk = null;
        this.currentOffset = 0;
      }
    }

    if (
      this.streamComplete &&
      !this.currentChunk &&
      this.queue.length === 0
    ) {
      this.streamComplete = false;

      if (this.playbackStarted) {
        this.playbackStarted = false;

        this.port.postMessage({
          type: 'playback_complete',
        });
      }
    }

    return true;
  }
}


registerProcessor(
  'tts-pcm-player',
  TtsPcmPlayerProcessor,
);
