import { CallRecord } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "In progress";
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export function CallDetailDialog({
  call,
  open,
  onOpenChange,
}: {
  call: CallRecord | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  if (!call) return null;

  const toolEvents = call.trace.filter((e) => e.type === "tool_call" || e.type === "tool_result");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            <span>{call.direction === "outbound" ? "Outbound" : call.direction}</span>
            <span className="text-muted-foreground">{call.phone ?? call.room_name}</span>
            <Badge variant="secondary">{call.status}</Badge>
          </DialogTitle>
          <p className="text-sm text-muted-foreground">
            {new Date(call.started_at).toLocaleString()} · {formatDuration(call.duration_seconds)}
          </p>
        </DialogHeader>

        <ScrollArea className="max-h-[60vh] pr-3">
          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Conversation</h3>
            {call.transcript.length === 0 ? (
              <p className="text-sm text-muted-foreground">No transcript captured.</p>
            ) : (
              call.transcript.map((line, index) => (
                <div
                  key={index}
                  className={
                    line.role === "assistant"
                      ? "rounded-lg bg-primary/5 p-3 text-sm"
                      : line.role === "tool"
                        ? "rounded-lg border border-dashed border-amber-300/60 bg-amber-50 p-3 text-sm dark:bg-amber-950/20"
                        : "rounded-lg bg-muted p-3 text-sm"
                  }
                >
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {line.role}
                    {line.tool ? ` · ${line.tool}` : ""}
                  </p>
                  <p className="whitespace-pre-wrap">{line.text}</p>
                </div>
              ))
            )}
          </section>

          <Separator className="my-4" />

          <section className="space-y-3 pb-2">
            <h3 className="text-sm font-semibold">Agent trace</h3>
            {toolEvents.length === 0 ? (
              <p className="text-sm text-muted-foreground">No tool usage recorded for this call.</p>
            ) : (
              toolEvents.map((event, index) => (
                <div key={index} className="rounded-lg border p-3 text-sm">
                  <p className="font-medium">{event.type === "tool_call" ? "Tool call" : "Tool result"}</p>
                  {event.tool ? <p className="text-muted-foreground">{event.tool}</p> : null}
                  {event.query ? <p className="mt-1">Query: {event.query}</p> : null}
                  {event.hits != null ? <p className="mt-1">Hits: {event.hits}</p> : null}
                  {event.sources?.length ? (
                    <p className="mt-1 text-muted-foreground">Sources: {event.sources.join(", ")}</p>
                  ) : null}
                  {event.preview ? <p className="mt-2 whitespace-pre-wrap text-xs">{event.preview}…</p> : null}
                  {event.at ? <p className="mt-1 text-xs text-muted-foreground">{event.at}</p> : null}
                </div>
              ))
            )}

            {call.trace.filter((e) => e.type === "status").length > 0 ? (
              <div className="rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">
                {call.trace
                  .filter((e) => e.type === "status")
                  .map((e, i) => (
                    <p key={i}>
                      {e.status} {e.at ? `@ ${new Date(e.at).toLocaleTimeString()}` : ""}
                    </p>
                  ))}
              </div>
            ) : null}
          </section>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
