import { Phone, BookOpen, Settings2, History, Shield, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import {
  api,
  type CallRecord,
  type Chunk,
  type DeskAgent,
  type JoinInfo,
  type KnowledgeMeta,
  type Source,
} from "./api";
import { CallDetailDialog } from "./components/CallDetailDialog";
import { PipelineStatus } from "./components/PipelineStatus";
import { CallRoom } from "./CallRoom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { InstructionsEditor } from "@/components/InstructionsEditor";
import ReactMarkdown from "react-markdown";

type Tab = "dial" | "knowledge" | "settings" | "logs";

function useTheme() {
  const [dark, setDark] = useState(() => {
    if (typeof window === "undefined") return false;
    const saved = localStorage.getItem("theme");
    if (saved === "dark") return true;
    if (saved === "light") return false;
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  return { dark, toggle: () => setDark((value) => !value) };
}

export function App() {
  const { dark, toggle: toggleTheme } = useTheme();
  const [tab, setTab] = useState<Tab>("dial");
  const [agent, setAgent] = useState<DeskAgent | null>(null);
  const [error, setError] = useState("");
  const [join, setJoin] = useState<JoinInfo | null>(null);
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [selectedCall, setSelectedCall] = useState<CallRecord | null>(null);

  async function refreshAgent() {
    setAgent(await api.agent());
  }

  async function refreshCalls() {
    setCalls(await api.calls());
  }

  useEffect(() => {
    refreshAgent().catch((err: Error) => setError(err.message));
    refreshCalls().catch(() => undefined);
  }, []);

  useEffect(() => {
    if (tab !== "logs") return;
    const timer = setInterval(() => {
      refreshCalls().catch(() => undefined);
    }, 4000);
    return () => clearInterval(timer);
  }, [tab]);

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-lg font-semibold">Cybercrime Helpline</h1>
              <p className="text-sm text-muted-foreground">Operations desk</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
            {agent ? (
              <Badge variant="outline">{agent.name}</Badge>
            ) : (
              <Skeleton className="h-6 w-24" />
            )}
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl gap-6 px-4 py-6 lg:grid-cols-[220px_1fr]">
        <nav className="flex flex-row gap-2 lg:flex-col">
          {(
            [
              ["dial", "Dial", Phone],
              ["knowledge", "Knowledge", BookOpen],
              ["settings", "Instructions", Settings2],
              ["logs", "Call logs", History],
            ] as const
          ).map(([key, label, Icon]) => (
            <Button
              key={key}
              variant={tab === key ? "default" : "ghost"}
              className="justify-start"
              onClick={() => setTab(key)}
            >
              <Icon className="mr-2 h-4 w-4" />
              {label}
            </Button>
          ))}
        </nav>

        <main className="min-w-0 space-y-4">
          {error ? (
            <Card className="border-destructive/40 bg-destructive/5">
              <CardContent className="py-3 text-sm text-destructive">{error}</CardContent>
            </Card>
          ) : null}

          {tab === "dial" && agent ? (
            <DialPanel
              agent={agent}
              join={join}
              onJoin={setJoin}
              onError={setError}
              onCallEnded={() => {
                setJoin(null);
                refreshCalls();
                setTab("logs");
              }}
            />
          ) : null}

          {tab === "knowledge" && agent ? (
            <KnowledgePanel agent={agent} onError={setError} />
          ) : null}

          {tab === "settings" && agent ? (
            <SettingsPanel
              agent={agent}
              onSaved={(next) => {
                setAgent(next);
                setError("");
              }}
              onError={setError}
            />
          ) : null}

          {tab === "logs" ? (
            <LogsPanel
              calls={calls}
              onSelect={(call) => setSelectedCall(call)}
              onRefresh={() => refreshCalls().catch((err: Error) => setError(err.message))}
            />
          ) : null}
        </main>
      </div>

      <CallDetailDialog
        call={selectedCall}
        open={selectedCall != null}
        onOpenChange={(open) => {
          if (!open) setSelectedCall(null);
        }}
      />
    </div>
  );
}

function DialPanel({
  agent,
  join,
  onJoin,
  onError,
  onCallEnded,
}: {
  agent: DeskAgent;
  join: JoinInfo | null;
  onJoin: (join: JoinInfo | null) => void;
  onError: (message: string) => void;
  onCallEnded: () => void;
}) {
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [callId, setCallId] = useState<string | null>(null);
  const [status, setStatus] = useState("idle");

  useEffect(() => {
    const activeCallId = callId ?? join?.call_id ?? null;
    if (!activeCallId) return;
    let stop = false;
    const poll = async () => {
      try {
        const call = await api.call(activeCallId);
        if (stop) return;
        setStatus(call.status);
        if (call.status === "ended" || call.status === "failed") {
          onJoin(null);
          onCallEnded();
        }
      } catch {
        /* keep polling */
      }
    };
    poll();
    const timer = setInterval(poll, 1500);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, [callId, join?.call_id, onCallEnded, onJoin]);

  async function startCall() {
    setBusy(true);
    onError("");
    onJoin(null);
    setCallId(null);
    setStatus("dispatched");
    try {
      const started = await api.phoneCall(phone);
      setCallId(started.call_id ?? null);
      setStatus("dispatched");

      for (let attempt = 0; attempt < 45; attempt += 1) {
        if (started.call_id) {
          const call = await api.call(started.call_id);
          setStatus(call.status);
          if (call.status === "ended" || call.status === "failed") {
            onCallEnded();
            return;
          }
        }
        const rooms = await api.rooms();
        const live = rooms.find((row) => row.name === started.room);
        if (live && live.participants >= 1) {
          onJoin(started);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      onError("Worker did not join the room in time. Check the worker terminal.");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Call failed");
      setStatus("idle");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Outbound call</CardTitle>
          <CardDescription>
            Dial a number, watch the pipeline, and monitor the conversation. The agent greets on
            pickup for inbound and outbound calls.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1 space-y-2">
              <Label htmlFor="phone">Phone number</Label>
              <Input
                id="phone"
                placeholder="+91..."
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>
            <Button disabled={busy || phone.length < 8} onClick={() => void startCall()}>
              {busy ? "Starting…" : "Call"}
            </Button>
          </div>

          {status !== "idle" ? (
            <div className="space-y--2">
              <p className="text-sm font-medium">Pipeline</p>
              <PipelineStatus status={status} />
            </div>
          ) : null}

          <p className="text-xs text-muted-foreground">
            Voice stack: {agent.stt_model} → {agent.llm_model} → {agent.tts_model}
          </p>
        </CardContent>
      </Card>

      {join ? (
        <Card>
          <CardHeader>
            <CardTitle>Live monitor</CardTitle>
            <CardDescription>Listen-only view of the active room.</CardDescription>
          </CardHeader>
          <CardContent>
            <CallRoom join={join} onLeave={() => onJoin(null)} />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function KnowledgePanel({ agent, onError }: { agent: DeskAgent; onError: (m: string) => void }) {
  const [sources, setSources] = useState<Source[]>([]);
  const [meta, setMeta] = useState<KnowledgeMeta | null>(null);
  const [collection, setCollection] = useState("incident_playbook");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const [viewSource, setViewSource] = useState<Source | null>(null);
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      setSources(await api.knowledge(agent.id));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not load knowledge");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    api.knowledgeMeta().then(setMeta).catch(() => undefined);
  }, [agent.id]);

  async function openChunks(source: Source) {
    setViewSource(source);
    setChunksLoading(true);
    try {
      setChunks(await api.chunks(source.id));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not load chunks");
    } finally {
      setChunksLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Knowledge base</CardTitle>
          <CardDescription>
            Documents are stored in collections for scoped retrieval. Playbooks can be tagged with
            an incident category.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="collection">Collection</Label>
              <select
                id="collection"
                className="mt-2 flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                value={collection}
                onChange={(e) => setCollection(e.target.value)}
              >
                {(meta?.collections ?? [{ id: "incident_playbook", label: "Incident playbook" }]).map(
                  (item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ),
                )}
              </select>
            </div>
            {collection === "incident_playbook" || collection === "reassurance" ? (
              <div>
                <Label htmlFor="category">Incident category (optional)</Label>
                <select
                  id="category"
                  className="mt-2 flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  <option value="">— Any —</option>
                  {(meta?.incident_categories ?? []).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
          </div>
          <div>
            <Label htmlFor="upload">Upload document</Label>
            <Input
              id="upload"
              type="file"
              accept=".txt,.md,.pdf,.docx,.pptx,.xlsx"
              className="mt-2"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                api
                  .upload(agent.id, file, collection, category || undefined)
                  .then(refresh)
                  .catch((err: Error) => onError(err.message));
                e.target.value = "";
              }}
            />
          </div>

          {loading ? (
            <Skeleton className="h-24 w-full" />
          ) : sources.length === 0 ? (
            <p className="text-sm text-muted-foreground">No documents uploaded yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>File</TableHead>
                  <TableHead>Collection</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Chunks</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sources.map((source) => (
                  <TableRow key={source.id}>
                    <TableCell className="font-medium">{source.filename}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{source.collection}</Badge>
                    </TableCell>
                    <TableCell>{source.category ?? "—"}</TableCell>
                    <TableCell>{source.chunk_count}</TableCell>
                    <TableCell className="text-right space-x-2">
                      <Button size="sm" variant="outline" onClick={() => void openChunks(source)}>
                        View chunks
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          api
                            .removeSource(source.id)
                            .then(refresh)
                            .catch((err: Error) => onError(err.message))
                        }
                      >
                        Remove
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={viewSource != null} onOpenChange={(open) => !open && setViewSource(null)}>
        <DialogContent className="max-h-[85vh] max-w-3xl">
          <DialogHeader>
            <DialogTitle>{viewSource?.filename} — chunks</DialogTitle>
          </DialogHeader>
          {chunksLoading ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <ScrollArea className="max-h-[60vh] pr-3">
              <div className="space-y-3">
                {chunks.map((chunk) => (
                  <div key={chunk.id} className="rounded-lg border p-3">
                    <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
                      <span>Chunk {chunk.index}</span>
                      <span>{chunk.char_count} chars</span>
                    </div>
                    <p className="whitespace-pre-wrap text-sm">{chunk.content}</p>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SettingsPanel({
  agent,
  onSaved,
  onError,
}: {
  agent: DeskAgent;
  onSaved: (agent: DeskAgent) => void;
  onError: (m: string) => void;
}) {
  const [instructions, setInstructions] = useState(agent.instructions);
  const [saving, setSaving] = useState(false);
  const dirty = instructions.trim() !== agent.instructions.trim();

  useEffect(() => {
    setInstructions(agent.instructions);
  }, [agent.instructions]);

  async function save() {
    setSaving(true);
    onError("");
    try {
      onSaved(await api.updateInstructions(instructions.trim()));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>System instructions</CardTitle>
        <CardDescription>
          Override the default helpline persona. Leave blank sections out — saving replaces the full
          prompt used on every call.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="instructions">Custom instructions</Label>
          <InstructionsEditor
            id="instructions"
            value={instructions}
            onChange={setInstructions}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={!dirty || saving} onClick={() => void save()}>
            {saving ? "Saving…" : "Save instructions"}
          </Button>
          <Button
            variant="outline"
            onClick={() => setInstructions(agent.default_instructions)}
          >
            Reset to default
          </Button>
        </div>
        <Separator />
        <details className="text-sm">
          <summary className="cursor-pointer font-medium">Default instructions</summary>
          <div className="mt-2 max-h-[360px] overflow-y-auto rounded-lg bg-muted p-3">
            <ReactMarkdown
              components={{
                h2: ({ children }) => (
                  <h2 className="mt-4 mb-2 text-sm font-semibold first:mt-0">{children}</h2>
                ),
                h3: ({ children }) => (
                  <h3 className="mt-3 mb-1 text-xs font-semibold">{children}</h3>
                ),
                p: ({ children }) => (
                  <p className="my-1.5 text-xs leading-relaxed text-muted-foreground">{children}</p>
                ),
                ul: ({ children }) => (
                  <ul className="my-1.5 list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
                    {children}
                  </ul>
                ),
                li: ({ children }) => <li className="leading-relaxed">{children}</li>,
              }}
            >
              {agent.default_instructions}
            </ReactMarkdown>
          </div>
        </details>
      </CardContent>
    </Card>
  );
}

function LogsPanel({
  calls,
  onSelect,
  onRefresh,
}: {
  calls: CallRecord[];
  onSelect: (call: CallRecord) => void;
  onRefresh: () => void;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Call logs</CardTitle>
          <CardDescription>Recent calls with transcript and agent tool trace.</CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={onRefresh}>
          Refresh
        </Button>
      </CardHeader>
      <CardContent>
        {calls.length === 0 ? (
          <p className="text-sm text-muted-foreground">No calls yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Direction</TableHead>
                <TableHead>Phone</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Turns</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {calls.map((call) => (
                <TableRow
                  key={call.id}
                  className="cursor-pointer"
                  onClick={() => onSelect(call)}
                >
                  <TableCell>{new Date(call.started_at).toLocaleString()}</TableCell>
                  <TableCell>{call.direction}</TableCell>
                  <TableCell>{call.phone ?? "—"}</TableCell>
                  <TableCell>
                    <Badge variant={call.status === "ended" ? "secondary" : "outline"}>
                      {call.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {call.duration_seconds != null ? `${call.duration_seconds}s` : "—"}
                  </TableCell>
                  <TableCell>{call.transcript.length}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
