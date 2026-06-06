class PCMPlayer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.hasStreamEnded = false; // inbound audio stream monitor
    this.hasNotifiedEnd = false; // notified system of audio stream end ?

    this.port.onmessage = (event) => {
      if (event.data.flush) {
        this.queue = [];
        this.hasStreamEnded = false; // reset stream end monitor
        this.hasNotifiedEnd = false; // reset notification flag
        return;
      }

      if (event.data.end) { // handle server message indicating end of stream
        this.hasStreamEnded = true;
        return;
      }

      const pcm = event.data; // Int16Array
      const f32 = new Float32Array(pcm.length);
      for (let i = 0; i < pcm.length; i++) {
        f32[i] = pcm[i] / 0x8000;
      }
      this.queue.push(f32);
    };
  }

  process(inputs, outputs) {
    const output = outputs[0][0]; // mono
    output.fill(0);

    if (this.queue.length > 0) {
      let chunk = this.queue[0];
      const framesToCopy = Math.min(output.length, chunk.length);

      output.set(chunk.subarray(0, framesToCopy));

      if (framesToCopy < chunk.length) {
        this.queue[0] = chunk.subarray(framesToCopy);
      } else {
        this.queue.shift();
      }
    }

    if(
      this.hasStreamEnded &&
      this.queue.length === 0 &&
      !this.hasNotifiedEnd
    ) {
      this.hasNotifiedEnd = true;
      this.port.postMessage({ type:'playback_complete' }); // inform the system that playback is complete
    }

    return true;
  }
}

registerProcessor("pcm-player", PCMPlayer);
