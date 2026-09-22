export type TranscriptItem = {
  id: string;
  start: number;
  end: number;
  text: string;
  isFinal: boolean;
};

export type KnowledgeCard = {
  id: string;
  subject: string;
  title: string;
  summary: string;
  keyPoints: string[];
  question: string;
  start: number;
  end: number;
  source: string;
};

export type SessionResult = {
  sessionId: string;
  subject: string;
  markdown: string;
  localPath: string;
  cardCount: number;
  llmStatus: 'disabled' | 'completed' | 'fallback';
  syncStatus: 'not_configured' | 'pending' | 'completed' | 'failed';
  notionPageId?: string;
  syncError?: string;
};

export type SessionState = {
  active: boolean;
  sessionId?: string;
  tabId?: number;
  title?: string;
  url?: string;
  platform?: string;
  startedAt?: number;
  currentTime?: number;
  duration?: number;
  paused?: boolean;
  serverStatus?: 'connecting' | 'connected' | 'error' | 'idle';
  error?: string;
  transcripts: TranscriptItem[];
  knowledgeCards: KnowledgeCard[];
  lastResult?: SessionResult;
};

export type ExtensionMessage =
  | { type: 'GET_SESSION_STATE' }
  | { type: 'SESSION_STATE'; payload: SessionState }
  | { type: 'VIDEO_STATE'; payload: Partial<SessionState> }
  | { type: 'START_CAPTURE'; payload: { streamId: string; token: string; session: SessionState } }
  | { type: 'STOP_CAPTURE' }
  | { type: 'STOP_SESSION' }
  | { type: 'CAPTURE_STATUS'; payload: { status: SessionState['serverStatus']; error?: string } }
  | { type: 'TRANSCRIPT_UPDATE'; payload: TranscriptItem }
  | { type: 'KNOWLEDGE_CARD'; payload: KnowledgeCard }
  | { type: 'ADD_MARK'; payload: { kind: 'important' | 'confusing' | 'recall'; note?: string } };
