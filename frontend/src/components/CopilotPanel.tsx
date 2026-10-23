import { Bot, Send } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ApiError, apiClient } from "../services/apiClient";
import type { CopilotAnswer, CopilotSource } from "../types/api";
import { Card, TextField, buttonStyles } from "./ui";

const DEFAULT_SUGGESTIONS = [
  "Summarise the latest scrutiny findings",
  "Why was the highest-severity finding raised?",
  "Which fields are missing or inconclusive?",
  "What is still unresolved?",
  "What evidence requests are outstanding?",
  "Compare the survey numbers across documents",
  "What is the status of the simulated issuer checks?",
  "What should I inspect next?",
];

interface Turn {
  question: string;
  answer?: CopilotAnswer;
  error?: string;
}

function SourceButton({ source, onOpenFinding }: { source: CopilotSource; onOpenFinding: (id: string) => void }) {
  const body = (
    <>
      <span className="font-mono text-xs text-ink-subtle">[{source.id}]</span> {source.label}
      {source.quote && <span className="block border-l-2 border-info-line pl-2 font-mono text-xs text-ink">“{source.quote}”</span>}
    </>
  );
  return source.finding_id ? (
    <button type="button" onClick={() => onOpenFinding(source.finding_id!)}
      className="w-full rounded border border-line bg-surface px-2 py-1 text-left text-sm hover:bg-info-bg focus-visible:outline-2 focus-visible:outline-saffron-500"
      aria-label={`Open source ${source.id}: ${source.label}`}>
      {body}
    </button>
  ) : <div className="rounded border border-line bg-surface px-2 py-1 text-sm">{body}</div>;
}

export function CopilotPanel({ applicationCode, onOpenFinding }: { applicationCode: string; onOpenFinding: (id: string) => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);

  async function ask(text: string) {
    const q = text.trim();
    if (q.length < 2 || busy) return;
    setBusy(true);
    setQuestion("");
    setTurns((t) => [...t, { question: q }]);
    try {
      const answer = await apiClient.askCopilot(applicationCode, q);
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, answer } : turn)));
    } catch (err) {
      const error = err instanceof ApiError ? err.message : "The assistant could not answer.";
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error } : turn)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Reviewer copilot">
      <div className="space-y-3">
        <p className="rounded-control border border-info-line bg-info-bg p-2 text-xs text-ink">
          <Bot aria-hidden="true" className="mr-1 inline h-4 w-4" />
          A reviewer aid that answers only from this application's stored findings, extracted evidence, evidence requests and
          simulated checks, with numbered sources. It does not make decisions or judge authenticity. No AI model is used.
        </p>
        <div className="flex flex-wrap gap-1" aria-label="Suggested questions">
          {DEFAULT_SUGGESTIONS.map((s) => (
            <button key={s} type="button" disabled={busy} onClick={() => ask(s)}
              className="rounded-full border border-line-strong bg-surface px-2.5 py-1 text-xs text-ink hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-saffron-500">
              {s}
            </button>
          ))}
        </div>
        <ol className="space-y-3" aria-label="Copilot conversation" aria-live="polite">
          {turns.map((t, i) => (
            <li key={i} className="space-y-2">
              <p className="ml-auto max-w-[85%] rounded-control bg-brand-800 px-3 py-2 text-sm text-white"><span className="sr-only">You asked: </span>{t.question}</p>
              {!t.answer && !t.error && <p role="status" className="text-sm text-ink-subtle">Looking up stored records…</p>}
              {t.error && <p role="alert" className="text-sm text-danger-700">{t.error}</p>}
              {t.answer && (
                <div className="space-y-2 rounded-control border border-line bg-surface p-3 text-sm" data-testid="copilot-answer">
                  {t.answer.lines.map((line, j) => <p key={j} className="whitespace-pre-wrap [overflow-wrap:anywhere]">{line}</p>)}
                  {!t.answer.grounded && (
                    <p className="text-xs font-medium text-warning-800">No supporting records were found for a factual answer.</p>
                  )}
                  {t.answer.limitations.map((l) => <p key={l} className="text-xs text-warning-800">Limitation: {l}</p>)}
                  {t.answer.sources.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">Sources</p>
                      {t.answer.sources.map((s) => <SourceButton key={s.id} source={s} onOpenFinding={onOpenFinding} />)}
                    </div>
                  )}
                </div>
              )}
            </li>
          ))}
        </ol>
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); void ask(question); }} className="flex items-end gap-2" aria-label="Ask the copilot">
          <div className="flex-1">
            <TextField label="Ask about this application" value={question} maxLength={500} onChange={(e) => setQuestion(e.target.value)} />
          </div>
          <button type="submit" className={buttonStyles.primary} disabled={busy || question.trim().length < 2}>
            <Send aria-hidden="true" className="h-4 w-4" /> Ask
          </button>
        </form>
      </div>
    </Card>
  );
}
