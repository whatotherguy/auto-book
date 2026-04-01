import { useEffect, useState } from "react"
import { ErrorBoundary } from "./components/ErrorBoundary"
import { ProjectsPage } from "./pages/ProjectsPage"
import { ProjectPage } from "./pages/ProjectPage"
import { ChapterReviewPage } from "./pages/ChapterReviewPage"
import { buildHashRoute, parseHashRoute } from "./routing"
import { getProject } from "./api"
import { cachedFetch } from "./cache"

export default function App() {
  const initialRoute = parseHashRoute(window.location.hash)
  const [projectId, setProjectId] = useState<number | null>(initialRoute.projectId)
  const [chapterId, setChapterId] = useState<number | null>(initialRoute.chapterId)
  const [projectName, setProjectName] = useState<string | null>(null)

  useEffect(() => {
    const nextHash = buildHashRoute(projectId, chapterId)
    if (window.location.hash !== nextHash) {
      window.location.hash = nextHash
    }
  }, [projectId, chapterId])

  // Fetch project name for breadcrumbs
  useEffect(() => {
    if (projectId) {
      cachedFetch(`project:${projectId}`, () => getProject(projectId), 120_000)
        .then((p) => setProjectName(p.name))
        .catch(() => setProjectName(null))
    } else {
      setProjectName(null)
    }
  }, [projectId])

  useEffect(() => {
    function handleHashChange() {
      const nextRoute = parseHashRoute(window.location.hash)
      setProjectId(nextRoute.projectId)
      setChapterId(nextRoute.chapterId)
    }

    window.addEventListener("hashchange", handleHashChange)
    return () => window.removeEventListener("hashchange", handleHashChange)
  }, [])

  return (
    <ErrorBoundary>
      {chapterId ? (
        <ChapterReviewPage
          key={chapterId}
          chapterId={chapterId}
          projectId={projectId}
          projectName={projectName}
          onBack={() => setChapterId(null)}
          onBackToProjects={() => { setChapterId(null); setProjectId(null) }}
        />
      ) : projectId ? (
        <ProjectPage
          projectId={projectId}
          onBack={() => setProjectId(null)}
          onOpenChapter={(nextChapterId) => {
            setChapterId(nextChapterId)
          }}
        />
      ) : (
        <ProjectsPage onOpenProject={setProjectId} />
      )}
    </ErrorBoundary>
  )
}
