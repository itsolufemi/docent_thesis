import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildInterruptedAssistantText,
} from '../src/audio/playbackHistory.js';


test(
  'interrupted history includes only completed sentences',
  () => {
    assert.equal(
      buildInterruptedAssistantText([
        'Sentence one.',
      ]),
      'Sentence one. [interrupted]',
    );
  },
);


test(
  'interruption before a completed sentence stores only the marker',
  () => {
    assert.equal(
      buildInterruptedAssistantText([]),
      '[interrupted]',
    );
  },
);
