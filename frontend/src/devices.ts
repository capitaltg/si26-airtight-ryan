// Audio device enumeration, the presenter's stored device choice, and input
// level metering. Split from audio.ts because none of it touches recording or
// playback: this module never sees a MediaRecorder or the shared playback
// element, and audio.ts never enumerates or persists anything.

import { useCallback, useEffect, useRef, useState } from "react"

import { openAudioStream } from "./audio"

export interface AudioDevice {
  deviceId: string
  label: string
}

const INPUT_KEY = "airtight.audio.input"
const OUTPUT_KEY = "airtight.audio.output"

// Root-mean-square level above which the mic counts as picking up sound. Set
// well above the noise floor of a silent room but below normal speech.
export const LEVEL_THRESHOLD = 0.02

// localStorage access throws outright in some private-browsing modes, so every
// read and write goes through these two.
function readStored(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStored(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    // Persistence is best-effort; the choice still applies to this session.
  }
}

function toDevices(all: MediaDeviceInfo[], kind: MediaDeviceKind): AudioDevice[] {
  return all.filter((d) => d.kind === kind).map((d) => ({ deviceId: d.deviceId, label: d.label }))
}

// The current input and output lists, re-enumerated whenever the OS reports a
// device change, so plugging in a headset updates both pickers without a
// reload. `labelsVisible` is false while every label is the empty string, which
// is what the browser reports before microphone permission has been granted —
// the panel uses it to offer a permission prompt rather than a list of blank
// rows.
export function useAudioDevices(): {
  inputs: AudioDevice[]
  outputs: AudioDevice[]
  labelsVisible: boolean
  refresh: () => Promise<void>
  error: string | null
} {
  const [inputs, setInputs] = useState<AudioDevice[]>([])
  const [outputs, setOutputs] = useState<AudioDevice[]>([])
  const [error, setError] = useState<string | null>(null)
  // Set on unmount so an in-flight enumerateDevices does not set state after.
  const goneRef = useRef(false)

  const refresh = useCallback(async () => {
    try {
      const all = await navigator.mediaDevices.enumerateDevices()
      if (goneRef.current) return
      setInputs(toDevices(all, "audioinput"))
      setOutputs(toDevices(all, "audiooutput"))
      setError(null)
    } catch (err) {
      if (goneRef.current) return
      setError(err instanceof Error ? err.message : "Could not list audio devices.")
    }
  }, [])

  useEffect(() => {
    goneRef.current = false
    void refresh()
    const onChange = () => void refresh()
    navigator.mediaDevices.addEventListener("devicechange", onChange)
    return () => {
      goneRef.current = true
      navigator.mediaDevices.removeEventListener("devicechange", onChange)
    }
  }, [refresh])

  const labelsVisible = [...inputs, ...outputs].some((d) => d.label !== "")

  return { inputs, outputs, labelsVisible, refresh, error }
}

// Write-through persistence for the presenter's device choice. Returns the
// stored ids verbatim; resolving one against the current device list is
// `resolveDeviceId`'s job, because a stored id is deliberately kept even while
// its device is unplugged.
export function useDevicePreferences(): {
  inputId: string | null
  outputId: string | null
  setInputId: (id: string | null) => void
  setOutputId: (id: string | null) => void
} {
  const [inputId, setInput] = useState<string | null>(() => readStored(INPUT_KEY))
  const [outputId, setOutput] = useState<string | null>(() => readStored(OUTPUT_KEY))

  const setInputId = useCallback((id: string | null) => {
    setInput(id)
    writeStored(INPUT_KEY, id)
  }, [])

  const setOutputId = useCallback((id: string | null) => {
    setOutput(id)
    writeStored(OUTPUT_KEY, id)
  }, [])

  return { inputId, outputId, setInputId, setOutputId }
}

// A stored id that is absent from the current list resolves to null, meaning
// system default. The stored value itself is left alone by design: a headset
// unplugged for one rehearsal and plugged back in for the next is reselected
// automatically instead of forgotten.
export function resolveDeviceId(storedId: string | null, devices: AudioDevice[]): string | null {
  if (!storedId) return null
  return devices.some((d) => d.deviceId === storedId) ? storedId : null
}

// Publishes a 0..1 root-mean-square level for `deviceId` while `active` is
// true. Opens its own stream rather than sharing useRecorder's: the meter lives
// exactly as long as the panel is open, the recorder lives exactly as long as
// one held button, and coupling them would mean either a metering stream left
// open through the whole rehearsal or a meter that dies whenever a recording
// ends.
export function useInputLevel(
  deviceId: string | null,
  active: boolean,
): { level: number; error: string | null } {
  const [level, setLevel] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!active) {
      setLevel(0)
      return
    }
    let cancelled = false
    let frame = 0
    let stream: MediaStream | null = null
    let context: AudioContext | null = null

    async function begin() {
      try {
        const opened = await openAudioStream(deviceId)
        // The effect was torn down while getUserMedia was in flight — release
        // the stream immediately or the mic indicator stays on with nothing
        // left to turn it off.
        if (cancelled) {
          opened.getTracks().forEach((t) => t.stop())
          return
        }
        stream = opened
        const ctx = new AudioContext()
        context = ctx
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 2048
        ctx.createMediaStreamSource(opened).connect(analyser)
        const samples = new Float32Array(analyser.fftSize)
        const tick = () => {
          analyser.getFloatTimeDomainData(samples)
          let sum = 0
          for (const s of samples) sum += s * s
          const rms = Math.sqrt(sum / samples.length)
          // Quantized so an unchanged level is a React state bail-out rather
          // than a re-render on every animation frame.
          setLevel(Math.round(Math.min(1, rms) * 100) / 100)
          frame = requestAnimationFrame(tick)
        }
        frame = requestAnimationFrame(tick)
        setError(null)
      } catch (err) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : "Microphone access was denied.")
      }
    }
    void begin()

    return () => {
      cancelled = true
      if (frame) cancelAnimationFrame(frame)
      stream?.getTracks().forEach((t) => t.stop())
      void context?.close()
      setLevel(0)
    }
  }, [deviceId, active])

  return { level, error }
}
