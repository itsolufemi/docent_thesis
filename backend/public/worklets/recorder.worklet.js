class PCMRecorderProcessor extends AudioWorkletProcessor {
  process(inputs, outputs) {
    const input = inputs[0];
    if (input && input[0]) {
      // Send Float32 samples back to the main thread
      this.port.postMessage(input[0]);
    }
    return true; // keep alive
  }
}

registerProcessor("pcm-recorder", PCMRecorderProcessor);
