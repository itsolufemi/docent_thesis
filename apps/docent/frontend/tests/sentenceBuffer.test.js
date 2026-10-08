import assert from 'node:assert/strict';
import test from 'node:test';

import {
  extractSpeakableSentences,
} from '../src/audio/sentenceBuffer.js';


test(
  'extracts complete sentences and retains the remainder',
  () => {
    const result =
      extractSpeakableSentences(
        'The Swing dates from 1767. It shows a young woman',
      );

    assert.deepEqual(
      result.sentences,
      ['The Swing dates from 1767.'],
    );
    assert.equal(
      result.remainder,
      'It shows a young woman',
    );
  },
);

test(
  'extracts multiple punctuation styles in order',
  () => {
    const result =
      extractSpeakableSentences(
        'Really? Yes! It is.',
      );

    assert.deepEqual(
      result.sentences,
      ['Really?', 'Yes!', 'It is.'],
    );
    assert.equal(result.remainder, '');
  },
);

test(
  'does not split at commas',
  () => {
    const result =
      extractSpeakableSentences(
        'Painted in 1767, it remains unfinished',
      );

    assert.deepEqual(
      result.sentences,
      [],
    );
    assert.equal(
      result.remainder,
      'Painted in 1767, it remains unfinished',
    );
  },
);
