// The persona's self-introduction, shown above the question on every surface
// that renders a prompt: the live card, the optimistic pending turn, and the
// completed turn in the scrollback. Muted and italic so it reads as the person
// introducing themself rather than as part of the ask. Renders nothing when
// there is no intro — which is every prompt except a persona's first.

export function PromptIntro({ intro }: { intro?: string | null }) {
  if (!intro) return null
  return (
    <p data-testid="prompt-intro" className="text-sm italic text-slate-500">
      {intro}
    </p>
  )
}
