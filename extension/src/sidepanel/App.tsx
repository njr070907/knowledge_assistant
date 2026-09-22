import { useEffect, useMemo, useState } from 'react';
import { Bookmark, CircleHelp, FileText, Settings, Square, Volume2 } from 'lucide-react';
import type { ExtensionMessage, SessionState, TranscriptItem } from '../types';

const initialState: SessionState = {
  active: false,
  serverStatus: 'idle',
  transcripts: [],
  knowledgeCards: [],
};

const isExtensionRuntime = typeof chrome !== 'undefined' && Boolean(chrome.runtime?.id);

const previewState: SessionState = {
  active: true,
  serverStatus: 'connected',
  sessionId: 'preview-session',
  title: '线性代数：矩阵的秩',
  platform: 'B站',
  startedAt: Date.now() - 1_122_000,
  currentTime: 1122,
  duration: 2840,
  paused: true,
  transcripts: [
    { id: 'p1', start: 1111, end: 1115, text: '所以我们可以对矩阵进行初等行变换，把它化为阶梯形矩阵。', isFinal: true },
    { id: 'p2', start: 1115, end: 1119, text: '这些变换不会改变矩阵的秩，因为它们对应可逆的线性操作。', isFinal: true },
    { id: 'p3', start: 1119, end: 1122, text: '因此，阶梯形矩阵中的非零行数就是原矩阵的秩。', isFinal: true },
  ],
  knowledgeCards: [
    {
      id: 'card-preview',
      subject: '线性代数',
      title: '初等变换不改变矩阵的秩',
      summary: '矩阵经过初等行变换或初等列变换后，其秩保持不变，因此可以化为更简单的形式来研究。',
      keyPoints: ['初等变换对应可逆的线性操作', '阶梯形矩阵的非零行数等于矩阵的秩'],
      question: '这个结论依赖哪些定义或不变量？请说明推理链。',
      start: 1111,
      end: 1122,
      source: 'local-rules',
    },
  ],
};

function formatTime(seconds = 0): string {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safeSeconds / 60);
  return `${String(minutes).padStart(2, '0')}:${String(safeSeconds % 60).padStart(2, '0')}`;
}

function TranscriptRow({ item }: { item: TranscriptItem }) {
  return (
    <li className="transcript-row">
      <time>{formatTime(item.start)}</time>
      <p>{item.text}</p>
    </li>
  );
}

export function App() {
  const [session, setSession] = useState<SessionState>(() => isExtensionRuntime ? initialState : previewState);
  const [answer, setAnswer] = useState('');
  const [notice, setNotice] = useState('');
  const [isFinishing, setIsFinishing] = useState(false);

  useEffect(() => {
    if (!isExtensionRuntime) return undefined;
    void chrome.runtime.sendMessage({ type: 'GET_SESSION_STATE' } satisfies ExtensionMessage).then((state) => {
      if (state) setSession(state as SessionState);
    });

    const listener = (message: ExtensionMessage) => {
      if (message.type === 'SESSION_STATE') setSession(message.payload);
    };
    chrome.runtime.onMessage.addListener(listener);
    return () => chrome.runtime.onMessage.removeListener(listener);
  }, []);

  const latest = session.transcripts.at(-1);
  const latestCard = session.knowledgeCards.at(-1);
  const currentKnowledge = useMemo(() => {
    if (latestCard) {
      return {
        title: latestCard.title,
        detail: latestCard.summary,
      };
    }
    if (!latest) {
      return {
        title: '等待第一个完整知识点',
        detail: '知流会先稳定转写，再在主题边界生成知识卡片。',
      };
    }
    return {
      title: latest.text.length > 26 ? `${latest.text.slice(0, 26)}…` : latest.text,
      detail: '当前为第一阶段的转写摘要；下一阶段会加入学科化推导、公式与前置知识关系。',
    };
  }, [latest, latestCard]);

  const mark = async (label: string, kind: 'important' | 'confusing' | 'recall', note?: string) => {
    if (isExtensionRuntime) {
      const response = await chrome.runtime.sendMessage({ type: 'ADD_MARK', payload: { kind, note } } satisfies ExtensionMessage);
      if (!response?.ok) {
        setNotice(response?.error ?? '记录失败');
        return;
      }
    }
    setNotice(`${label}已记录在 ${formatTime(session.currentTime)}`);
    window.setTimeout(() => setNotice(''), 2200);
  };

  const stop = async () => {
    setIsFinishing(true);
    if (isExtensionRuntime) {
      await chrome.runtime.sendMessage({ type: 'STOP_SESSION' } satisfies ExtensionMessage);
    } else {
      setSession((current) => ({
        ...current,
        active: false,
        serverStatus: 'idle',
        lastResult: {
          sessionId: current.sessionId ?? 'preview-session',
          subject: current.knowledgeCards.at(-1)?.subject ?? '通用课程',
          markdown: '# 预览笔记',
          localPath: 'server/data/notes/preview-session.md',
          cardCount: current.knowledgeCards.length,
          llmStatus: 'disabled',
          syncStatus: 'not_configured',
        },
      }));
    }
    setIsFinishing(false);
  };

  if (!session.active) {
    return (
      <main className="app-shell empty-shell">
        <header className="brand-bar">
          <div><strong>知流</strong><span>在观看中，把知识留下来</span></div>
          <Settings aria-hidden="true" size={20} />
        </header>
        <section className="empty-state">
          <div className="empty-mark">{session.lastResult ? <FileText size={30} /> : <Volume2 size={30} />}</div>
          <h1>{session.lastResult ? '本次学习已整理' : '准备开始学习'}</h1>
          {session.lastResult ? (
            <div className="result-summary">
              <p>{session.lastResult.subject} · {session.lastResult.cardCount} 个知识点</p>
              <p>{session.lastResult.syncStatus === 'completed' ? '已同步至 Notion' : session.lastResult.syncStatus === 'failed' ? 'Notion 同步失败，已保留本地重试任务' : '笔记已保存在本机；配置 Notion 后可同步'}</p>
            </div>
          ) : (
            <p>打开 B 站、YouTube 或抖音视频，然后点击浏览器工具栏中的“知流”图标。</p>
          )}
          {session.error ? <p className="error-copy">{session.error}</p> : null}
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="brand-bar">
        <div><strong>知流</strong><span>在观看中，把知识留下来</span></div>
        <button className="icon-button" aria-label="设置"><Settings size={20} /></button>
      </header>

      <section className="session-strip" aria-label="学习状态">
        <div className="session-copy">
          <span className={`record-dot ${session.serverStatus === 'connected' ? 'is-live' : ''}`} />
          <div><strong>{session.serverStatus === 'connected' ? '正在学习' : '正在连接'}</strong><p>{session.title}</p></div>
        </div>
        <div className="session-time"><span>{formatTime(session.currentTime)}</span><Volume2 size={20} /></div>
      </section>

      {session.error ? <div className="error-banner">{session.error}</div> : null}

      <section className="content-section">
        <div className="section-heading"><h2>当前知识点</h2><span>根据视频内容实时生成</span></div>
        <article className="knowledge-note">
          <div><h3>{currentKnowledge.title}</h3><p>{currentKnowledge.detail}</p></div>
          <FileText size={24} aria-hidden="true" />
        </article>
      </section>

      <section className="content-section transcript-section">
        <div className="section-heading"><h2>实时字幕</h2><span>本机识别 · 滚动更新</span></div>
        {session.transcripts.length > 0 ? (
          <ol className="transcript-list">
            {session.transcripts.slice(-12).map((item) => <TranscriptRow key={item.id} item={item} />)}
          </ol>
        ) : (
          <p className="transcript-placeholder">正在等待语音。视频开始播放后，稳定片段会出现在这里。</p>
        )}
      </section>

      {session.paused && session.transcripts.length > 0 ? (
        <section className="recall-panel">
          <div className="recall-title"><span>Ⅱ</span><div><h2>暂停一下，回忆刚才的内容</h2><p>不看视频，试着回答后再继续。</p></div></div>
          <label htmlFor="recall-answer">问题：{latestCard?.question ?? '刚才这个知识点解决了什么问题？'}</label>
          <textarea id="recall-answer" value={answer} maxLength={200} onChange={(event) => setAnswer(event.target.value)} placeholder="请输入你的答案…" />
          <div className="answer-actions"><span>{answer.length} / 200</span><button onClick={() => void mark('回答', 'recall', answer)}>保存回答</button></div>
        </section>
      ) : null}

      <div className="footer-spacer" />
      <footer className="sticky-actions">
        <button className="primary-action" disabled={isFinishing} onClick={() => void stop()}><Square size={16} fill="currentColor" />{isFinishing ? '正在整理' : '结束学习'}</button>
        <button onClick={() => void mark('重点', 'important')}><Bookmark size={19} />标记重点</button>
        <button onClick={() => void mark('疑问', 'confusing')}><CircleHelp size={19} />没听懂</button>
      </footer>
      {notice ? <div className="toast" role="status">{notice}</div> : null}
    </main>
  );
}
