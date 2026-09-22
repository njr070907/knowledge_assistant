import type { ExtensionMessage } from './types';

let lastSignature = '';

function findPrimaryVideo(): HTMLVideoElement | undefined {
  const videos = Array.from(document.querySelectorAll<HTMLVideoElement>('video'));
  return [...videos].sort((a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight)[0];
}

function publishVideoState(): void {
  const video = findPrimaryVideo();
  if (!video) return;

  const payload = {
    title: document.title,
    url: location.href,
    currentTime: Number.isFinite(video.currentTime) ? video.currentTime : 0,
    duration: Number.isFinite(video.duration) ? video.duration : undefined,
    paused: video.paused,
  };
  const signature = `${Math.floor(payload.currentTime)}:${payload.paused}:${payload.title}:${payload.url}`;
  if (signature === lastSignature) return;
  lastSignature = signature;

  void chrome.runtime.sendMessage({ type: 'VIDEO_STATE', payload } satisfies ExtensionMessage).catch(() => undefined);
}

setInterval(publishVideoState, 1000);
document.addEventListener('play', publishVideoState, true);
document.addEventListener('pause', publishVideoState, true);
window.addEventListener('popstate', publishVideoState);
