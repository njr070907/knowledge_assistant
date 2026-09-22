import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

test('48 kHz input produces 16 kHz PCM without cross-frame phase drift', async () => {
  const source = await readFile(new URL('../public/audio-worklet.js', import.meta.url), 'utf8');
  const emitted = [];
  let Processor;

  class AudioWorkletProcessorStub {
    port = {
      postMessage(buffer) {
        emitted.push(buffer);
      },
    };
  }

  vm.runInNewContext(source, {
    AudioWorkletProcessor: AudioWorkletProcessorStub,
    Int16Array,
    Math,
    sampleRate: 48000,
    registerProcessor(_name, Constructor) {
      Processor = Constructor;
    },
  });

  const processor = new Processor({ processorOptions: { targetSampleRate: 16000 } });
  for (let index = 0; index < 375; index += 1) {
    processor.process([[new Float32Array(128).fill(0.25)]]);
  }

  const outputSamples = emitted.reduce((total, buffer) => total + buffer.byteLength / 2, 0);
  assert.equal(outputSamples, 16000);
  assert.equal(emitted.length, 10);
});

