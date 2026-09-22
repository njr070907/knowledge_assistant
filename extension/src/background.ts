import type { ExtensionMessage, SessionState, TranscriptItem } from './types';

const SESSION_KEY = 'zhiliuSession';
const OFFSCREEN_PATH = 'offscreen.html';

const emptySession = (): SessionState => ({
  active: false,
  serverStatus: 'idle',
  transcripts: [],
  knowledgeCards: [],
});

async function getSession(): Promise<SessionState> {
  const stored = await chrome.storage.session.get(SESSION_KEY);
  const value = stored[SESSION_KEY] as SessionState | undefined;
  if (!value) return emptySession();
  return {
    ...emptySession(),
    ...value,
    transcripts: value.transcripts ?? [],
    knowledgeCards: value.knowledgeCards ?? [],
  };
}

async function saveSession(next: SessionState): Promise<void> {
  await chrome.storage.session.set({ [SESSION_KEY]: next });
  void chrome.runtime.sendMessage({ type: 'SESSION_STATE', payload: next } satisfies ExtensionMessage).catch(() => undefined);
}

async function ensureOffscreenDocument(): Promise<void> {
  if (await chrome.offscreen.hasDocument()) return;
  await chrome.offscreen.createDocument({
    url: OFFSCREEN_PATH,
    reasons: [chrome.offscreen.Reason.USER_MEDIA],
    justification: 'Capture the user-selected video tab and stream audio to the local transcription service.',
  });
}

function inferPlatform(url?: string): string {
  if (!url) return '网页视频';
  if (url.includes('bilibili.com')) return 'B站';
  if (url.includes('youtube.com')) return 'YouTube';
  if (url.includes('douyin.com')) return '抖音';
  return '网页视频';
}

function getMediaStreamId(targetTabId: number): Promise<string> {
  return new Promise((resolve, reject) => {
    chrome.tabCapture.getMediaStreamId({ targetTabId }, (streamId) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else resolve(streamId);
    });
  });
}

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id) return;

  try {
    const streamPromise = getMediaStreamId(tab.id);
    const panelPromise = chrome.sidePanel.open({ tabId: tab.id });
    const [streamId] = await Promise.all([streamPromise, panelPromise]);
    await ensureOffscreenDocument();

    const token = crypto.randomUUID();
    const session: SessionState = {
      active: true,
      sessionId: crypto.randomUUID(),
      tabId: tab.id,
      title: tab.title ?? '未命名视频',
      url: tab.url,
      platform: inferPlatform(tab.url),
      startedAt: Date.now(),
      currentTime: 0,
      paused: false,
      serverStatus: 'connecting',
      transcripts: [],
      knowledgeCards: [],
    };

    await saveSession(session);
    await chrome.runtime.sendMessage({
      type: 'START_CAPTURE',
      payload: { streamId, token, session },
    } satisfies ExtensionMessage);
  } catch (error) {
    const current = await getSession();
    await saveSession({
      ...current,
      active: false,
      serverStatus: 'error',
      error: error instanceof Error ? error.message : String(error),
    });
  }
});

chrome.runtime.onMessage.addListener((message: ExtensionMessage, sender, sendResponse) => {
  if (message.type === 'GET_SESSION_STATE') {
    void getSession().then(sendResponse);
    return true;
  }

  if (message.type === 'VIDEO_STATE') {
    void (async () => {
      const current = await getSession();
      if (!current.active || (sender.tab?.id && current.tabId !== sender.tab.id)) return;
      await saveSession({ ...current, ...message.payload });
    })();
    return false;
  }

  if (message.type === 'CAPTURE_STATUS') {
    void (async () => {
      const current = await getSession();
      await saveSession({
        ...current,
        serverStatus: message.payload.status,
        error: message.payload.error,
      });
    })();
    return false;
  }

  if (message.type === 'TRANSCRIPT_UPDATE') {
    void (async () => {
      const current = await getSession();
      const transcripts: TranscriptItem[] = [...current.transcripts, message.payload].slice(-80);
      await saveSession({ ...current, transcripts });
    })();
    return false;
  }

  if (message.type === 'KNOWLEDGE_CARD') {
    void (async () => {
      const current = await getSession();
      const knowledgeCards = [...current.knowledgeCards, message.payload].slice(-20);
      await saveSession({ ...current, knowledgeCards });
    })();
    return false;
  }

  if (message.type === 'ADD_MARK') {
    void (async () => {
      const current = await getSession();
      if (!current.sessionId) throw new Error('没有正在进行的学习会话');
      const response = await fetch(`http://127.0.0.1:8765/api/sessions/${current.sessionId}/marks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kind: message.payload.kind,
          video_seconds: current.currentTime ?? 0,
          note: message.payload.note,
        }),
      });
      if (!response.ok) throw new Error(`记录失败：${response.status}`);
      sendResponse({ ok: true });
    })().catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : String(error) }));
    return true;
  }

  if (message.type === 'STOP_SESSION') {
    void (async () => {
      await chrome.runtime.sendMessage({ type: 'STOP_CAPTURE' } satisfies ExtensionMessage).catch(() => undefined);
      await new Promise((resolve) => setTimeout(resolve, 250));
      const current = await getSession();
      let lastResult = current.lastResult;
      let error = current.error;
      if (current.sessionId) {
        const response = await fetch(`http://127.0.0.1:8765/api/sessions/${current.sessionId}/finalize`, { method: 'POST' });
        if (response.ok) lastResult = await response.json();
        else error = `课后整理失败：${response.status}`;
      }
      await saveSession({ ...current, active: false, serverStatus: 'idle', lastResult, error });
      sendResponse({ ok: !error, result: lastResult, error });
    })().catch(async (caught) => {
      const current = await getSession();
      const error = caught instanceof Error ? caught.message : String(caught);
      await saveSession({ ...current, active: false, serverStatus: 'error', error });
      sendResponse({ ok: false, error });
    });
    return true;
  }

  return false;
});
