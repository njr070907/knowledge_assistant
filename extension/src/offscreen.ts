import type { ExtensionMessage, KnowledgeCard, SessionState, TranscriptItem } from './types';

let audioContext: AudioContext | undefined;
let mediaStream: MediaStream | undefined;
let socket: WebSocket | undefined;

async function stopCapture(): Promise<void> {
  socket?.close(1000, 'session-ended');
  socket = undefined;
  mediaStream?.getTracks().forEach((track) => track.stop());
  mediaStream = undefined;
  if (audioContext && audioContext.state !== 'closed') await audioContext.close();
  audioContext = undefined;
}

function reportStatus(status: SessionState['serverStatus'], error?: string): void {
  void chrome.runtime.sendMessage({
    type: 'CAPTURE_STATUS',
    payload: { status, error },
  } satisfies ExtensionMessage).catch(() => undefined);
}

async function startCapture(streamId: string, token: string, session: SessionState): Promise<void> {
  await stopCapture();

  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: {
        chromeMediaSource: 'tab',
        chromeMediaSourceId: streamId,
      },
    } as MediaTrackConstraints,
    video: false,
  });

  audioContext = new AudioContext();
  await audioContext.audioWorklet.addModule(chrome.runtime.getURL('audio-worklet.js'));

  const source = audioContext.createMediaStreamSource(mediaStream);
  const processor = new AudioWorkletNode(audioContext, 'pcm-processor', {
    processorOptions: { targetSampleRate: 16000 },
  });
  const silentOutput = audioContext.createGain();
  silentOutput.gain.value = 0;

  source.connect(audioContext.destination);
  source.connect(processor).connect(silentOutput).connect(audioContext.destination);

  socket = new WebSocket(`ws://127.0.0.1:8765/ws/audio?token=${encodeURIComponent(token)}`);
  socket.binaryType = 'arraybuffer';
  socket.addEventListener('open', () => {
    socket?.send(JSON.stringify({
      type: 'session_start',
      sessionId: session.sessionId,
      title: session.title,
      url: session.url,
      platform: session.platform,
      sampleRate: 16000,
    }));
    reportStatus('connected');
  });
  socket.addEventListener('message', (event) => {
    if (typeof event.data !== 'string') return;
    try {
      const payload = JSON.parse(event.data) as { type: string; [key: string]: unknown };
      if (payload.type === 'transcript') {
        const transcript: TranscriptItem = {
          id: String(payload.id),
          start: Number(payload.start),
          end: Number(payload.end),
          text: String(payload.text),
          isFinal: Boolean(payload.isFinal),
        };
        void chrome.runtime.sendMessage({ type: 'TRANSCRIPT_UPDATE', payload: transcript } satisfies ExtensionMessage).catch(() => undefined);
      } else if (payload.type === 'knowledge_card') {
        const card: KnowledgeCard = {
          id: String(payload.id),
          subject: String(payload.subject),
          title: String(payload.title),
          summary: String(payload.summary),
          keyPoints: Array.isArray(payload.keyPoints) ? payload.keyPoints.map(String) : [],
          question: String(payload.question),
          start: Number(payload.start),
          end: Number(payload.end),
          source: String(payload.source ?? 'local-rules'),
        };
        void chrome.runtime.sendMessage({ type: 'KNOWLEDGE_CARD', payload: card } satisfies ExtensionMessage).catch(() => undefined);
      } else if (payload.type === 'error') {
        reportStatus('error', String(payload.message ?? '本地服务处理失败'));
      }
    } catch {
      reportStatus('error', '本地服务返回了无法解析的数据');
    }
  });
  socket.addEventListener('error', () => reportStatus('error', '无法连接本机服务，请先运行 server/scripts/run.ps1'));
  socket.addEventListener('close', (event) => {
    if (event.code !== 1000) reportStatus('error', '本机服务连接已断开');
  });

  processor.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
    if (socket?.readyState === WebSocket.OPEN) socket.send(event.data);
  };
}

chrome.runtime.onMessage.addListener((message: ExtensionMessage) => {
  if (message.type === 'START_CAPTURE') {
    const { streamId, token, session } = message.payload;
    void startCapture(streamId, token, session).catch((error) => {
      reportStatus('error', error instanceof Error ? error.message : String(error));
    });
  }
  if (message.type === 'STOP_CAPTURE') void stopCapture();
  return false;
});
