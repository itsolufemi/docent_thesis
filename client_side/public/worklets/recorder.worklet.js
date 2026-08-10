const SPEECH_THRESHOLD = 0.025;
const SPEECH_START_DURATION_MS = 90;
const SPEECH_END_SILENCE_MS = 600;
const PRE_ROLL_DURATION_MS = 250;


class PCMRecorderProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    this.isSpeechActive = false;

    this.consecutiveSpeechSamples = 0;
    this.consecutiveSilenceSamples = 0;

    this.preRollFrames = [];
    this.preRollSampleCount = 0;

    this.minimumSpeechSamples = Math.round(
      sampleRate * (
        SPEECH_START_DURATION_MS / 1000
      ),
    );

    this.maximumSilenceSamples = Math.round(
      sampleRate * (
        SPEECH_END_SILENCE_MS / 1000
      ),
    );

    this.maximumPreRollSamples = Math.round(
      sampleRate * (
        PRE_ROLL_DURATION_MS / 1000
      ),
    );
  }

  calculateRms(samples) {
    let sumOfSquares = 0;

    for (
      let index = 0;
      index < samples.length;
      index += 1
    ) {
      const sample = samples[index];
      sumOfSquares += sample * sample;
    }

    return Math.sqrt(
      sumOfSquares / samples.length,
    );
  }

  addToPreRoll(samples) {
    const copiedSamples = new Float32Array(samples);

    this.preRollFrames.push(copiedSamples);
    this.preRollSampleCount += copiedSamples.length;

    while (
      this.preRollSampleCount >
        this.maximumPreRollSamples &&
      this.preRollFrames.length > 1
    ) {
      const removedFrame =
        this.preRollFrames.shift();

      this.preRollSampleCount -=
        removedFrame.length;
    }
  }

  process(inputs) {
    const input = inputs[0];
    const channel = input?.[0];

    if (!channel) {
      return true;
    }

    const samples = new Float32Array(channel);
    const rms = this.calculateRms(samples);
    const frameIsSpeech =
      rms >= SPEECH_THRESHOLD;

    if (!this.isSpeechActive) {
      this.addToPreRoll(samples);

      if (frameIsSpeech) {
        this.consecutiveSpeechSamples +=
          samples.length;
      } else {
        this.consecutiveSpeechSamples = 0;
      }

      if (
        this.consecutiveSpeechSamples >=
        this.minimumSpeechSamples
      ) {
        this.isSpeechActive = true;
        this.consecutiveSilenceSamples = 0;

        const preRollFrames =
          this.preRollFrames;

        this.preRollFrames = [];
        this.preRollSampleCount = 0;

        this.port.postMessage({
          type: 'speech_start',
          rms,
          preRollFrames,
        });

        this.consecutiveSpeechSamples = 0;
      }

      return true;
    }

    this.port.postMessage({
      type: 'audio_frame',
      samples,
      rms,
    });

    if (frameIsSpeech) {
      this.consecutiveSilenceSamples = 0;
    } else {
      this.consecutiveSilenceSamples +=
        samples.length;
    }

    if (
      this.consecutiveSilenceSamples >=
      this.maximumSilenceSamples
    ) {
      const silenceDurationMs = Math.round(
        (
          this.consecutiveSilenceSamples /
          sampleRate
        ) * 1000,
      );

      this.isSpeechActive = false;
      this.consecutiveSilenceSamples = 0;
      this.consecutiveSpeechSamples = 0;

      this.port.postMessage({
        type: 'speech_end',
        silenceDurationMs,
      });
    }

    return true;
  }
}


registerProcessor(
  'pcm-recorder',
  PCMRecorderProcessor,
);
