class PcmProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetRate = options.processorOptions?.targetSampleRate ?? 16000;
    this.ratio = sampleRate / this.targetRate;
    this.pending = [];
    this.phase = 0;
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel || channel.length === 0) return true;

    let position = this.phase;
    for (; position < channel.length; position += this.ratio) {
      const index = Math.floor(position);
      const next = Math.min(index + 1, channel.length - 1);
      const fraction = position - index;
      const sample = channel[index] * (1 - fraction) + channel[next] * fraction;
      this.pending.push(Math.max(-1, Math.min(1, sample)));
    }
    this.phase = position - channel.length;

    if (this.pending.length >= 1600) {
      const chunk = this.pending.splice(0, 1600);
      const pcm = new Int16Array(chunk.length);
      for (let i = 0; i < chunk.length; i += 1) {
        pcm[i] = chunk[i] < 0 ? chunk[i] * 32768 : chunk[i] * 32767;
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }
    return true;
  }
}

registerProcessor('pcm-processor', PcmProcessor);
