// The confirm step for abandoning a voice take. Rehearsal owns the recorded
// blob, the in-flight transcription, and every state change; this component
// only asks the question and reports which button was pressed.
//
// `kind` is what is being abandoned, and it changes only the keep label: a
// stopped recording can still be used, while an in-flight transcription can
// only be waited on.

import { Button } from "./ui/Button"
import { Modal } from "./ui/Modal"

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
    // No `onClose`: this dialog has no dismiss affordance today and must be
    // answered, so passing one would add Escape-to-dismiss that
    // cancel-recording.spec.ts does not expect.
    <Modal
      open
      label="Discard this recording?"
      size="sm"
      aria-modal="true"
      data-testid="discard-recording"
    >
      <h2 className="text-heading font-semibold text-text-strong">Discard this recording?</h2>
      <p className="text-body-sm text-text-muted">You&apos;ll answer this question again.</p>
      <div className="flex items-center justify-end gap-2">
        <Button variant="secondary" data-testid="discard-recording-keep" onClick={onKeep}>
          {kind === "recording" ? "Use recording" : "Keep waiting"}
        </Button>
        <Button variant="primary" data-testid="discard-recording-discard" onClick={onDiscard}>
          Discard take
        </Button>
      </div>
    </Modal>
  )
}
