export function buildInterruptedAssistantText(
  completedSentences,
) {
  return [
    ...(completedSentences ?? []),
    '[interrupted]',
  ].join(' ').trim();
}
