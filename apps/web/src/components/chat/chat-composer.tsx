"use client";

import { useCallback, useRef } from "react";
import { SendIcon, SquareIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const MAX_QUERY_LENGTH = 2000;

type ChatComposerProps = {
  draft: string;
  onDraftChange: (value: string) => void;
  onSubmit: (query: string) => void;
  onCancel: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  placeholder?: string;
};

export function ChatComposer({
  draft,
  onDraftChange,
  onSubmit,
  onCancel,
  isStreaming,
  disabled = false,
  placeholder = "Ask a regulatory question…",
}: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const remaining = MAX_QUERY_LENGTH - draft.length;

  const handleSubmit = useCallback(() => {
    const trimmed = draft.trim();
    if (!trimmed || isStreaming || disabled) return;
    onSubmit(trimmed);
  }, [draft, isStreaming, disabled, onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  return (
    <div className="space-y-2">
      <div className="relative">
        <Textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={isStreaming || disabled}
          maxLength={MAX_QUERY_LENGTH}
          rows={3}
          className="resize-none pr-12"
          aria-label="Query"
          aria-describedby="composer-hint"
        />
      </div>

      <div className="flex items-center justify-between gap-2">
        <p
          id="composer-hint"
          className={cn(
            "text-xs",
            remaining < 200 ? "text-destructive" : "text-muted-foreground",
          )}
        >
          {isStreaming ? "Receiving response…" : `${remaining.toLocaleString()} characters remaining · Shift+Enter for new line`}
        </p>

        <div className="flex items-center gap-2">
          {isStreaming && (
            <Button
              variant="outline"
              size="sm"
              onClick={onCancel}
              aria-label="Cancel streaming response"
            >
              <SquareIcon className="size-3.5" aria-hidden />
              Cancel
            </Button>
          )}

          {!isStreaming && (
            <Button
              size="sm"
              onClick={handleSubmit}
              disabled={!draft.trim() || disabled}
              aria-label="Submit query"
            >
              <SendIcon className="size-3.5" aria-hidden />
              Send
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
