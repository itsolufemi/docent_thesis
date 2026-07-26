import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

import {
  calculateRemainingSilenceMs,
  calculateRms,
} from '../src/audio/vadMath.js';


const SAMPLE_RATE = 16_000;
const FRAME_SAMPLE_COUNT = 128;


function createWorkletHarness() {
  const messages = [];
  let Processor = null;

  class TestAudioWorkletProcessor {
    constructor() {
      this.port = {
        postMessage(message) {
          messages.push(message);
        },
      };
    }
  }

  const context = vm.createContext({
    AudioWorkletProcessor: TestAudioWorkletProcessor,
    Float32Array,
    Math,
    console,
    sampleRate: SAMPLE_RATE,
    registerProcessor(name, processorClass) {
      assert.equal(name, 'pcm-recorder');
      Processor = processorClass;
    },
  });

  const workletSource = readFileSync(
    new URL(
      '../public/worklets/recorder.worklet.js',
      import.meta.url,
    ),
    'utf8',
  );

  vm.runInContext(
    workletSource,
    context,
    {
      filename: 'recorder.worklet.js',
    },
  );

  assert.ok(Processor);

  return {
    messages,
    processor: new Processor(),
  };
}


function processFrames(
  processor,
  {
    amplitude,
    frameCount,
  },
) {
  for (
    let frameIndex = 0;
    frameIndex < frameCount;
    frameIndex += 1
  ) {
    const samples =
      new Float32Array(FRAME_SAMPLE_COUNT);
    samples.fill(amplitude);
    processor.process([[samples]]);
  }
}


test('calculateRms handles silence and constant energy', () => {
  assert.equal(
    calculateRms(new Float32Array()),
    0,
  );
  assert.ok(
    Math.abs(
      calculateRms(
        new Float32Array([0.02, -0.02]),
      ) - 0.02,
    ) < 1e-6,
  );
});


test(
  'remaining silence accounts for processing time',
  () => {
    const timing = {
      initialSilenceMs: 600,
      forcedFinalisationSilenceMs: 1_800,
    };

    assert.equal(
      calculateRemainingSilenceMs({
        ...timing,
        speechEndedAtMs: null,
        nowMs: 5_000,
      }),
      1_200,
    );

    assert.equal(
      calculateRemainingSilenceMs({
        ...timing,
        speechEndedAtMs: 4_000,
        nowMs: 5_500,
      }),
      300,
    );

    assert.equal(
      calculateRemainingSilenceMs({
        ...timing,
        speechEndedAtMs: 3_000,
        nowMs: 5_500,
      }),
      0,
    );
  },
);


test(
  'worklet ignores silence and opens consecutive VAD segments',
  () => {
    const {
      messages,
      processor,
    } = createWorkletHarness();

    processFrames(
      processor,
      {
        amplitude: 0,
        frameCount: Math.ceil(
          (SAMPLE_RATE * 5) /
          FRAME_SAMPLE_COUNT,
        ),
      },
    );

    assert.deepEqual(messages, []);

    processFrames(
      processor,
      {
        amplitude: 0.03,
        frameCount: 5,
      },
    );

    const firstSpeechStart = messages.at(-1);
    assert.equal(
      firstSpeechStart.type,
      'speech_start',
    );

    const preRollSamples =
      firstSpeechStart.preRollFrames.reduce(
        (total, frame) => total + frame.length,
        0,
      );

    assert.ok(preRollSamples >= 640);
    assert.ok(preRollSamples <= 4_128);

    processFrames(
      processor,
      {
        amplitude: 0.03,
        frameCount: 1,
      },
    );

    assert.equal(
      messages.at(-1).type,
      'audio_frame',
    );

    processFrames(
      processor,
      {
        amplitude: 0,
        frameCount: 75,
      },
    );

    const firstSpeechEnd = messages.at(-1);
    assert.equal(
      firstSpeechEnd.type,
      'speech_end',
    );
    assert.equal(
      firstSpeechEnd.silenceDurationMs,
      600,
    );

    const messageCountAfterFirstSegment =
      messages.length;

    processFrames(
      processor,
      {
        amplitude: 0,
        frameCount: 100,
      },
    );

    assert.equal(
      messages.length,
      messageCountAfterFirstSegment,
    );

    processFrames(
      processor,
      {
        amplitude: 0.03,
        frameCount: 5,
      },
    );

    assert.equal(
      messages.at(-1).type,
      'speech_start',
    );
    assert.equal(
      messages.filter(
        (message) => message.type === 'speech_start',
      ).length,
      2,
    );
  },
);
