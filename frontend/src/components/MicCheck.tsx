// The mic check panel: pick an input, watch its level, record five seconds and
// play it back, pick an output, hear a test tone. Rendered without chrome so
// each call site supplies its own container (a collapsible section on the
// landing screen, a modal in session). The ids it selects are the ids the
// rehearsal itself records and plays with — this is not a parallel preview.

import { useEffect, useRef, useState } from "react"

import {
  openAudioStream,
  outputSelectionSupported,
  playTestTone,
  setOutputDevice,
  useRecorder,
} from "../audio"
import { LEVEL_THRESHOLD, resolveDeviceId, useAudioDevices, useInputLevel } from "../devices"
import type { AudioDevice } from "../devices"
import { Button } from "./ui/Button"
import { MicroCaps } from "./ui/MicroCaps"
import { Select } from "./ui/Select"

// Auto-stop for the loopback recording. Long enough to say a sentence, short
// enough that a presenter who walks away does not leave the mic open.
const MAX_TEST_SECONDS = 5
const LEVEL_SEGMENTS = 12

function DevicePicker({
  id,
  label,
  devices,
  value,
  onChange,
  testId,
}: {
  id: string
  label: string
  devices: AudioDevice[]
  value: string | null
  onChange: (id: string | null) => void
  testId: string
}) {
  return (
    <div className="space-y-1">
      <MicroCaps as="label" htmlFor={id} className="block">
        {label}
      </MicroCaps>
      <Select
        id={id}
        data-testid={testId}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
      >
        <option value="">System default</option>
        {devices.map((d, i) => (
          <option key={d.deviceId} value={d.deviceId}>
            {d.label || `Device ${i + 1}`}
          </option>
        ))}
      </Select>
    </div>
  )
}

function ErrorLine({ message }: { message: string }) {
  return (
    <p data-testid="mic-error" className="text-body-sm text-crimson-700">
      {message}
    </p>
  )
}

export function MicCheck({
  inputId,
  outputId,
  onInputChange,
  onOutputChange,
  onClose,
}: {
  inputId: string | null
  outputId: string | null
  onInputChange: (id: string | null) => void
  onOutputChange: (id: string | null) => void
  onClose?: () => void
}) {
  const { inputs, outputs, labelsVisible, refresh, error: listError } = useAudioDevices()
  const [permissionError, setPermissionError] = useState<string | null>(null)
  const [asking, setAsking] = useState(false)

  const resolvedInput = resolveDeviceId(inputId, inputs)
  const resolvedOutput = resolveDeviceId(outputId, outputs)
  // A stored choice whose device is gone: the picker shows System default, and
  // this line says so, so a silent fallback is not mistaken for the stored
  // choice still being in effect.
  const inputMissing = inputId !== null && resolvedInput === null && labelsVisible
  const outputMissing = outputId !== null && resolvedOutput === null && labelsVisible

  // Re-apply the resolved output to the shared playback element whenever it
  // changes. `Rehearsal` already applies it once at mount, but that is not
  // enough on its own: `setSinkId` silently no-ops until the page holds
  // device-info permission (audio.ts's swallow-on-reject is deliberate), so a
  // stored non-default output only takes effect once permission is granted —
  // which happens here, inside the panel, after Rehearsal's mount-time effect
  // already ran. Re-firing here on every resolution change (including the one
  // triggered by a `devicechange` re-enumeration) is what keeps the picker's
  // displayed choice and the shared element's actual sink from silently
  // diverging.
  useEffect(() => {
    void setOutputDevice(resolvedOutput)
  }, [resolvedOutput, labelsVisible])

  // Metering starts only once labels are visible, i.e. permission is granted:
  // opening the metering stream *is* the prompt, and the panel offers an
  // explicit button for that instead.
  const metering = labelsVisible && permissionError === null
  const { level, error: levelError } = useInputLevel(resolvedInput, metering)

  // Latched verdict, so the live region announces the useful transition once
  // rather than narrating an animation frame by frame. Reset when the selected
  // input changes, since that is a new question.
  const [heard, setHeard] = useState(false)
  useEffect(() => {
    if (level > LEVEL_THRESHOLD) setHeard(true)
  }, [level])
  useEffect(() => {
    setHeard(false)
  }, [resolvedInput])

  const recorder = useRecorder(inputId)
  const [clipUrl, setClipUrl] = useState<string | null>(null)
  const clipUrlRef = useRef<string | null>(null)
  const autoStopRef = useRef<number | null>(null)
  const clipElRef = useRef<HTMLAudioElement | null>(null)

  function revokeClip() {
    if (clipUrlRef.current) URL.revokeObjectURL(clipUrlRef.current)
    clipUrlRef.current = null
  }

  // Same discipline as the transcript's recorded answers (Rehearsal.tsx): the
  // previous object URL is revoked before a new recording starts and again on
  // unmount, so the panel cannot leak a blob for the tab's life.
  useEffect(() => {
    return () => {
      revokeClip()
      if (autoStopRef.current) window.clearTimeout(autoStopRef.current)
    }
  }, [])

  async function stopTest() {
    if (autoStopRef.current) {
      window.clearTimeout(autoStopRef.current)
      autoStopRef.current = null
    }
    const blob = await recorder.stop()
    if (blob.size === 0) return
    const url = URL.createObjectURL(blob)
    clipUrlRef.current = url
    setClipUrl(url)
  }

  async function startTest() {
    revokeClip()
    setClipUrl(null)
    await recorder.start()
    autoStopRef.current = window.setTimeout(() => void stopTest(), MAX_TEST_SECONDS * 1000)
  }

  // Play the loopback through the selected output too, where the browser
  // supports it — otherwise the check would prove the mic and lie about the
  // speakers.
  useEffect(() => {
    const el = clipElRef.current as
      | (HTMLAudioElement & { setSinkId?: (id: string) => Promise<void> })
      | null
    if (!el || typeof el.setSinkId !== "function") return
    void el.setSinkId(resolvedOutput ?? "").catch(() => {
      // An unroutable output must not break playback of the clip itself.
    })
  }, [clipUrl, resolvedOutput])

  async function askPermission() {
    setAsking(true)
    setPermissionError(null)
    try {
      const stream = await openAudioStream(null)
      // Release it right away: the meter opens its own stream, this call exists
      // only to make the browser grant permission and reveal device labels.
      stream.getTracks().forEach((t) => t.stop())
      await refresh()
    } catch (err) {
      setPermissionError(err instanceof Error ? err.message : "Microphone access was denied.")
    } finally {
      setAsking(false)
    }
  }

  const filled = Math.min(LEVEL_SEGMENTS, Math.round(level * LEVEL_SEGMENTS))

  return (
    <div data-testid="mic-check" className="space-y-4 text-left">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-heading font-semibold text-text-strong">Mic check</h2>
          <p className="text-body-sm text-text-muted">
            The devices you pick here are the ones this rehearsal records and plays with.
          </p>
        </div>
        {onClose && (
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        )}
      </div>

      {listError && <ErrorLine message={listError} />}

      {/* 1. Microphone */}
      {!labelsVisible ? (
        <div className="space-y-2">
          <Button variant="primary" onClick={askPermission} disabled={asking}>
            {asking ? "Asking…" : "Allow microphone access"}
          </Button>
          <p className="text-body-sm text-text-muted">
            The browser needs permission before it will name your microphones.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <DevicePicker
            id="mic-check-input"
            testId="mic-input-select"
            label="Microphone"
            devices={inputs}
            value={resolvedInput}
            onChange={onInputChange}
          />
          {inputs.length === 0 && (
            <p className="text-body-sm text-text-muted">No microphone found.</p>
          )}
          {inputMissing && (
            <p className="text-body-sm text-text-muted">
              The microphone you picked before is not connected. Using the system default.
            </p>
          )}
          {/* Purely visual: the status line below carries the same information
              as text, so no ARIA widget role here. */}
          <div className="flex gap-1" aria-hidden="true">
            {Array.from({ length: LEVEL_SEGMENTS }, (_, i) => (
              <div
                key={i}
                className={`h-2 flex-1 rounded-pill transition-colors ${
                  i < filled ? "bg-moss-600" : "bg-sand-300"
                }`}
              />
            ))}
          </div>
          <p
            data-testid="mic-level-status"
            aria-live="polite"
            className="text-body-sm text-text-body"
          >
            {heard ? "Microphone is picking up sound" : "No sound detected yet"}
          </p>
        </div>
      )}
      {permissionError && <ErrorLine message={permissionError} />}
      {levelError && <ErrorLine message={levelError} />}

      {/* 2. Test recording */}
      <div className="space-y-2 border-t border-subtle pt-3">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => void (recorder.recording ? stopTest() : startTest())}
        >
          {recorder.recording ? "Stop" : "Record a test clip"}
        </Button>
        <p className="text-body-sm text-text-muted">
          Up to {MAX_TEST_SECONDS} seconds, played straight back. Nothing is sent anywhere.
        </p>
        {clipUrl && (
          <>
            {/* oxlint-disable-next-line jsx-a11y/media-has-caption */}
            <audio
              ref={clipElRef}
              data-testid="mic-test-clip"
              src={clipUrl}
              controls
              className="w-full"
            />
          </>
        )}
        {recorder.error && <ErrorLine message={recorder.error} />}
      </div>

      {/* 3. Speakers */}
      <div className="space-y-2 border-t border-subtle pt-3">
        {outputSelectionSupported() && (
          <>
            <DevicePicker
              id="mic-check-output"
              testId="mic-output-select"
              label="Speakers"
              devices={outputs}
              value={resolvedOutput}
              onChange={onOutputChange}
            />
            {outputMissing && (
              <p className="text-body-sm text-text-muted">
                The speakers you picked before are not connected. Using the system default.
              </p>
            )}
          </>
        )}
        <Button variant="secondary" size="sm" onClick={() => void playTestTone()}>
          Play test sound
        </Button>
        {!outputSelectionSupported() && (
          <p className="text-body-sm text-text-muted">
            This browser cannot choose an output device. The sound plays wherever your system sends
            it.
          </p>
        )}
      </div>
    </div>
  )
}
