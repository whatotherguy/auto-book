import { useEffect, useState } from "react"
import { ErrorBoundary } from "./components/ErrorBoundary"
import { ProjectsPage } from "./pages/ProjectsPage"
import { ProjectPage } from "./pages/ProjectPage"
import { ChapterReviewPage } from "./pages/ChapterReviewPage"
import { buildHashRoute, parseHashRoute } from "./routing"

export default function App() {
  const initialRoute = parseHashRoute(window.location.hash)
  const [projectId, setProjectId] = useState<number | null>(initialRoute.projectId)
  const [chapterId, setChapterId] = useState<number | null>(initialRoute.chapterId)

  useEffect(() => {
    const nextHash = buildHashRoute(projectId, chapterId)
    if (window.location.hash !== nextHash) {
      window.location.hash = nextHash
    }
  }, [projectId, chapterId])

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
          chapterId={chapterId}
          onBack={() => setChapterId(null)}
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
