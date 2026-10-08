const SENTENCE_END_PATTERN =
  /([.!?]+)(?=\s|$)/g;


export function extractSpeakableSentences(
  text,
) {
  const sentences = [];
  let consumedUntil = 0;
  let match;

  SENTENCE_END_PATTERN.lastIndex = 0;

  while (
    (
      match =
        SENTENCE_END_PATTERN.exec(text)
    ) !== null
  ) {
    const endIndex =
      match.index + match[0].length;
    const candidate =
      text
        .slice(
          consumedUntil,
          endIndex,
        )
        .trim();

    consumedUntil = endIndex;

    if (candidate) {
      sentences.push(candidate);
    }
  }

  return {
    sentences,
    remainder:
      text
        .slice(consumedUntil)
        .trimStart(),
  };
}
