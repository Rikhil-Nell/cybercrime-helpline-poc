export type DeskAgent = {
  id: string;
  name: string;
  instructions: string;
  default_instructions: string;
  stt_model: string;
  llm_model: string;
  tts_model: string;
};

export type Source = {
  id: string;
  filename: string;
  collection: string;
  category: string | null;
  chunk_count: number;
  created_at?: string;
};

export type KnowledgeMeta = {
  collections: { id: string; label: string }[];
  incident_categories: { id: string; label: string }[];
};

export type Chunk = {
  id: string;
  index: number;
  content: string;
  char_count: number;
};

export type TraceEvent = {
  type: string;
  at?: string;
  status?: string;
  tool?: string;
  query?: string;
  hits?: number;
  preview?: string;
  sources?: string[];
  phone?: string;
  error?: string;
};

export type TranscriptLine = {
  role: string;
  text: string;
  tool?: string;
  hits?: number;
};

export type CallRecord = {
  id: string;
  agent_id: string | null;
  room_name: string;
  direction: string;
  phone: string | null;
  status: string;
  transcript: TranscriptLine[];
  trace: TraceEvent[];
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
};

export type LiveRoom = {
  name: string;
  participants: number;
  created_at: string | null;
};

export type JoinInfo = {
  room: string;
  url: string;
  token: string;
  mode?: "listen" | "publish";
  status?: string;
  phone?: string;
  call_id?: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.json() as Promise<T>;
}

export const api = {
  agent: () => request<DeskAgent>("/api/agent"),
  updateInstructions: (instructions: string) =>
    request<DeskAgent>("/api/agent", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instructions }),
    }),
  knowledge: (agentId: string) => request<Source[]>(`/api/agents/${agentId}/knowledge`),
  knowledgeMeta: () => request<KnowledgeMeta>("/api/knowledge/collections"),
  chunks: (sourceId: string) => request<Chunk[]>(`/api/knowledge/${sourceId}/chunks`),
  upload: (agentId: string, file: File, collection: string, category?: string) => {
    const body = new FormData();
    body.append("file", file);
    body.append("collection", collection);
    if (category) body.append("category", category);
    return request<Source>(`/api/agents/${agentId}/knowledge`, { method: "POST", body });
  },
  removeSource: (id: string) => request<{ ok: boolean }>(`/api/knowledge/${id}`, { method: "DELETE" }),
  phoneCall: (phone: string) =>
    request<JoinInfo>("/api/calls/phone", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone }),
    }),
  call: (id: string) => request<CallRecord>(`/api/calls/${id}`),
  calls: () => request<CallRecord[]>("/api/calls"),
  rooms: () => request<LiveRoom[]>("/api/rooms"),
};

export const PIPELINE_STEPS = [
  { key: "dispatched", label: "Dispatched" },
  { key: "worker_joined", label: "Worker ready" },
  { key: "ringing", label: "Ringing" },
  { key: "answered", label: "Answered" },
  { key: "active", label: "Conversation" },
  { key: "ended", label: "Complete" },
] as const;

export function pipelineIndex(status: string): number {
  const order = PIPELINE_STEPS.map((step) => step.key);
  if (status === "dialing" || status === "idle") return 0;
  if (status === "failed") return 2;
  const idx = order.indexOf(status as (typeof order)[number]);
  return idx >= 0 ? idx : 0;
}
