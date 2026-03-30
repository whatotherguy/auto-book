import { ChangeEvent, FormEvent, useEffect, useId, useState } from "react"
import { createChapter, deleteChapter, getProject, getProjectChapters, uploadChapterAudio, uploadChapterText, uploadChapterTextFile } from "../api"
import { Chapter, Project } from "../types"
import { CollapsibleSection } from "../components/CollapsibleSection"

export function ProjectPage({
  projectId,
  onBack,
  onOpenChapter
}: {
  projectId: number
  onBack: () => void
  onOpenChapter: (id: number) => void
}) {
  const chapterNumberId = useId()
  const titleId = useId()
  const audioId = useId()
  const manuscriptFileId = useId()
  const manuscriptTextId = useId()
  const createHelpId = useId()

  const [project, setProject] = useState<Project | null>(null)
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [chapterNumber, setChapterNumber] = useState(1)
  const [title, setTitle] = useState("")
  const [text, setText] = useState("")
  const [audioFile, setAudioFile] = useState<File | null>(null)
  const [manuscriptFile, setManuscriptFile] = useState<File | null>(null)
  const [textFileName, setTextFileName] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function loadChapters() {
    try {
      setError(null)
      setProject(await getProject(projectId))
      const loadedChapters = await getProjectChapters(projectId)
      setChapters(loadedChapters)
      if (loadedChapters.length > 0) {
        const maxNumber = Math.max(...loadedChapters.map((c) => c.chapter_number))
        setChapterNumber(maxNumber + 1)
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to load chapters.")
    }
  }

  useEffect(() => {
    loadChapters()
  }, [projectId])

  function handleAudioChange(event: ChangeEvent<HTMLInputElement>) {
    setAudioFile(event.target.files?.[0] ?? null)
  }

  function handleTextFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) {
      setManuscriptFile(null)
      setTextFileName(null)
      return
    }

    setManuscriptFile(file)
    setTextFileName(file.name)
  }

  async function handleCreateChapter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSaving(true)
    setError(null)

    try {
      const chapter = await createChapter(projectId, chapterNumber, title.trim() || undefined)
      if (manuscriptFile) {
        await uploadChapterTextFile(chapter.id, manuscriptFile)
      } else if (text.trim()) {
        await uploadChapterText(chapter.id, text)
      }
      if (audioFile) {
        await uploadChapterAudio(chapter.id, audioFile)
      }

      setTitle("")
      setText("")
      setAudioFile(null)
      setManuscriptFile(null)
      setTextFileName(null)
      await loadChapters()
      onOpenChapter(chapter.id)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to create chapter.")
    } finally {
      setIsSaving(false)
    }
  }

  async function handleDeleteChapter(chapterId: number) {
    if (!window.confirm("Delete this chapter and its saved artifacts?")) {
      return
    }

    try {
      setError(null)
      await deleteChapter(chapterId)
      await loadChapters()
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to delete chapter.")
    }
  }

  return (
    <div className="page app-shell">
      <button type="button" onClick={onBack}>Back to Projects</button>
      <div className="page-hero compact">
        <p className="eyebrow">Project Workspace</p>
        <h1>{project?.name ?? `Project ${projectId}`}</h1>
        <p className="hero-copy">
          Create chapters, load source assets, and move directly into review once the material is ready.
        </p>
      </div>

      <CollapsibleSection
        title="Create Chapter"
        subtitle="Add the source audio and manuscript before analysis."
      >
        <form onSubmit={handleCreateChapter}>
          <p id={createHelpId} className="muted">
            If you upload both a manuscript file and pasted text, the uploaded file wins. Keep pasted text handy for quick tests or small corrections.
          </p>
          <label htmlFor={chapterNumberId}>Chapter number</label>
          <input
            id={chapterNumberId}
            name="chapterNumber"
            type="number"
            min={1}
            step={1}
            inputMode="numeric"
            value={chapterNumber}
            onChange={(e) => {
              const nextValue = Number.parseInt(e.target.value, 10)
              setChapterNumber(Number.isNaN(nextValue) ? 1 : nextValue)
            }}
          />
          <label htmlFor={titleId}>Title</label>
          <input
            id={titleId}
            name="title"
            autoComplete="off"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Optional chapter title"
            aria-describedby={createHelpId}
          />
          <label htmlFor={audioId}>Chapter WAV</label>
          <input
            id={audioId}
            name="chapterAudio"
            type="file"
            accept=".wav,audio/wav"
            onChange={handleAudioChange}
          />
          <p className="muted">Upload the original chapter WAV. The app keeps the source file intact and works from a local analysis copy.</p>
          <label htmlFor={manuscriptFileId}>Chapter text file</label>
          <input
            id={manuscriptFileId}
            name="chapterTextFile"
            type="file"
            accept=".txt,.pdf,text/plain,application/pdf"
            onChange={handleTextFileChange}
          />
          <p className="muted">TXT is preferred. PDF is accepted when you need to capture the chapter manuscript from an exported file.</p>
          {textFileName ? <div className="muted">Loaded manuscript file: {textFileName}</div> : null}
          <label htmlFor={manuscriptTextId}>Paste manuscript text</label>
          <textarea
            id={manuscriptTextId}
            name="manuscriptText"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={12}
            placeholder="Paste the chapter manuscript here"
          />
          <button type="submit" disabled={isSaving}>
            {isSaving ? "Saving…" : "Create and Open Chapter"}
          </button>
        </form>
      </CollapsibleSection>

      {error ? <div className="card error" role="alert">{error}</div> : null}

      <CollapsibleSection title="Chapters" subtitle={`${chapters.length} available`}>
        {chapters.length === 0 ? <p className="muted">No chapters yet. Create one above to begin the review workflow.</p> : null}
        <div className="list">
          {chapters.map((chapter) => (
            <div key={chapter.id} className="list-item-row">
              <button
                type="button"
                className="list-item list-item-grow"
                onClick={() => onOpenChapter(chapter.id)}
                aria-label={`Open chapter ${chapter.chapter_number}${chapter.title ? `: ${chapter.title}` : ""}`}
              >
                Chapter {chapter.chapter_number}
                {chapter.title ? `: ${chapter.title}` : ""}
              </button>
              <button type="button" className="danger-button" onClick={() => handleDeleteChapter(chapter.id)}>
                Delete
              </button>
            </div>
          ))}
        </div>
      </CollapsibleSection>
    </div>
  )
}
