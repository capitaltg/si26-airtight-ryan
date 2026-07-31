// The confirm step for abandoning a voice take. Rehearsal owns the recorded
// blob, the in-flight transcription, and every state change; this component
// only asks the question and reports which button was pressed.
//
// `kind` is what is being abandoned, and it changes only the keep label: a
// stopped recording can still be used, while an in-flight transcription can
// only be waited on.

export function DiscardRecordingDialog({
  kind,
  onKeep,
  onDiscard,
}: {
  kind: "recording" | "transcribing"
  onKeep: () => void
  onDiscard: () => void
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/50 p-4">
      {/* Native <dialog> (open, not showModal, same as the mic check modal in
          Rehearsal) rather than a plain div with role="dialog": it carries the
          dialog semantics for free and satisfies the linter's
          prefer-tag-over-role rule without a suppression comment. */}
      <dialog
        open
        aria-modal="true"
        aria-label="Discard this recording?"
        data-testid="discard-recording"
        className="relative m-0 w-full max-w-sm space-y-3 rounded-lg bg-white p-4 shadow-lg"
      >
        <h2 className="text-sm font-semibold text-slate-800">Discard this recording?</h2>
        <p className="text-xs text-slate-500">You&apos;ll answer this question again.</p>
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            data-testid="discard-recording-keep"
            onClick={onKeep}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50"
          >
            {kind === "recording" ? "Use recording" : "Keep waiting"}
          </button>
          <button
            type="button"
            data-testid="discard-recording-discard"
            onClick={onDiscard}
            className="rounded-lg bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-700"
          >
            Discard take
          </button>
        </div>
      </dialog>
    </div>
  )
}
