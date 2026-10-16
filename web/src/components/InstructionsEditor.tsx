import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const markdownComponents = {
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="mt-5 mb-2 text-base font-semibold first:mt-0">{children}</h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="mt-4 mb-1.5 text-sm font-semibold">{children}</h3>
  ),
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="my-2 text-sm leading-relaxed text-foreground/90">{children}</p>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="my-2 list-disc space-y-1 pl-5 text-sm">{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="my-2 list-decimal space-y-1 pl-5 text-sm">{children}</ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li className="leading-relaxed text-foreground/90">{children}</li>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="font-semibold text-foreground">{children}</strong>
  ),
  code: ({ children }: { children?: React.ReactNode }) => (
    <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">{children}</code>
  ),
};

type InstructionsEditorProps = {
  id: string;
  value: string;
  onChange: (value: string) => void;
  minHeightClass?: string;
};

export function InstructionsEditor({
  id,
  value,
  onChange,
  minHeightClass = "min-h-[280px]",
}: InstructionsEditorProps) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <Textarea
        autoFocus
        id={id}
        className={cn(minHeightClass, "font-mono text-sm")}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => setEditing(false)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            setEditing(false);
          }
        }}
      />
    );
  }

  return (
    <button
      type="button"
      id={id}
      aria-label="Edit instructions"
      onClick={() => setEditing(true)}
      className={cn(
        minHeightClass,
        "w-full cursor-text rounded-md border border-input bg-background px-3 py-3 text-left shadow-xs transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      )}
    >
      {value.trim() ? (
        <div className="max-h-[480px] overflow-y-auto pr-1">
          <ReactMarkdown components={markdownComponents}>{value}</ReactMarkdown>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Click to add instructions…</p>
      )}
      <p className="mt-3 border-t border-border/60 pt-2 text-xs text-muted-foreground">
        Click to edit as markdown
      </p>
    </button>
  );
}
