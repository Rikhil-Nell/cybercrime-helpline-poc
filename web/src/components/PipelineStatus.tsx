import { PIPELINE_STEPS, pipelineIndex } from "@/api";
import { cn } from "@/lib/utils";

export function PipelineStatus({ status }: { status: string }) {
  const current = pipelineIndex(status);
  const failed = status === "failed";

  return (
    <ol className="flex flex-wrap gap-2">
      {PIPELINE_STEPS.map((step, index) => {
        const done = index < current || (status === "ended" && step.key === "ended");
        const active = index === current && status !== "ended" && !failed;
        return (
          <li
            key={step.key}
            className={cn(
              "rounded-full border px-3 py-1 text-xs font-medium",
              done && "border-primary/30 bg-primary/10 text-primary",
              active && "border-primary bg-primary text-primary-foreground",
              !done && !active && "border-border bg-muted text-muted-foreground",
              failed && step.key === "ringing" && "border-destructive bg-destructive/10 text-destructive",
            )}
          >
            {step.label}
          </li>
        );
      })}
      {failed ? <li className="rounded-full border border-destructive px-3 py-1 text-xs text-destructive">Failed</li> : null}
    </ol>
  );
}
