export type RouteState = {
  projectId: number | null
  chapterId: number | null
}

export function parseHashRoute(hash: string): RouteState {
  const normalized = hash.replace(/^#\/?/, "")

  const chapterMatch = normalized.match(/^project\/(\d+)\/chapter\/(\d+)$/)
  if (chapterMatch) {
    return { projectId: Number(chapterMatch[1]), chapterId: Number(chapterMatch[2]) }
  }

  const projectMatch = normalized.match(/^project\/(\d+)$/)
  if (projectMatch) {
    return { projectId: Number(projectMatch[1]), chapterId: null }
  }

  const legacyChapterMatch = normalized.match(/^chapter\/(\d+)$/)
  if (legacyChapterMatch) {
    return { projectId: null, chapterId: Number(legacyChapterMatch[1]) }
  }

  return { projectId: null, chapterId: null }
}

export function buildHashRoute(projectId: number | null, chapterId: number | null) {
  if (projectId != null && chapterId != null) {
    return `#/project/${projectId}/chapter/${chapterId}`
  }

  if (projectId != null) {
    return `#/project/${projectId}`
  }

  return "#/"
}
