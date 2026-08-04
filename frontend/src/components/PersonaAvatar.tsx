import { miniavs } from "@dicebear/collection"
import { createAvatar } from "@dicebear/core"

const cache = new Map<string, string>()

function avatarUri(personaId: string): string {
  const hit = cache.get(personaId)
  if (hit !== undefined) return hit

  let uri = ""
  try {
    uri = createAvatar(miniavs, { seed: personaId }).toDataUri()
  } catch {
    uri = ""
  }
  cache.set(personaId, uri)
  return uri
}

export function PersonaAvatar({ personaId, size = 28 }: { personaId: string; size?: number }) {
  const uri = avatarUri(personaId)
  if (!uri) return null

  return (
    <img
      src={uri}
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      data-testid="persona-avatar"
      data-persona={personaId}
      className="shrink-0 rounded-pill bg-sand-200"
      style={{ width: size, height: size }}
    />
  )
}
