export function calculateRms(samples) {
  if (!samples.length) {
    return 0;
  }

  let sumOfSquares = 0;

  for (
    let index = 0;
    index < samples.length;
    index += 1
  ) {
    sumOfSquares +=
      samples[index] * samples[index];
  }

  return Math.sqrt(
    sumOfSquares / samples.length,
  );
}
