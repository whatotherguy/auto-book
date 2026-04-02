import { ChangeEvent, FormEvent, useEffect, useId, useState } from "react"
import { createChapter, deleteChapter, getProject, getProjectChapters, uploadChapterAudio, uploadChapterText, uploadChapterTextFile } from "../api"
import { Chapter, Project } from "../types"
import { CollapsibleSection } from "../components/CollapsibleSection"
import { Breadcrumb } from "../components/Breadcrumb"
import { ConfirmModal } from "../components/ConfirmModal"
import { SkeletonListItems } from "../components/Skeleton"
import { formatTimecode } from "../utils"

function ChapterStatusBadges({ chapter }: { chapter: Chapter }) {
  const hasAudio = chapter.has_audio || !!chapter.audio_file_path
  const hasText = !!chapter.raw_text
  const isAnalyzed = !!chapter.analysis_artifact_updated_at
  const source = chapter.transcript_source

  return (
    <div className="rich-card-badges">
      <span className={`status-dot${hasAudio ? " on" : ""}`} title={hasAudio ? "Audio uploaded" : "No audio"} />
      <span className={`status-badge${hasAudio ? " ready" : " dim"}`}>{hasAudio ? "WAV" : "No audio"}</span>
      <span className={`status-dot${hasText ? " on" : ""}`} title={hasText ? "Manuscript loaded" : "No manuscript"} />
      <span className={`status-badge${hasText ? " ready" : " dim"}`}>{hasText ? "Text" : "No text"}</span>
      {isAnalyzed ? (
        <>
          <span className="status-dot on analyzed" title="Analyzed" />
          <span className="status-badge analyzed">Analyzed{source ? ` (${source.replace("faster-whisper-word-timestamps", "local").replace("openai-whisper-api", "API")})` : ""}</span>
        </>
      ) : hasAudio && hasText ? (
        <span className="status-badge dim">Not analyzed</span>
      ) : null}
    </div>
  )
}

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
  const [loading, setLoading] = useState(true)
  const [deleteTarget, setDeleteTarget] = useState<Chapter | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [isDeleting, setIsDeleting] = useState(false)
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false)

  const selectMode = selected.size > 0

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
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadChapters() }, [projectId])

  function handleAudioChange(event: ChangeEvent<HTMLInputElement>) {
    setAudioFile(event.target.files?.[0] ?? null)
  }

  function handleTextFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) { setManuscriptFile(null); setTextFileName(null); return }
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
      if (audioFile) await uploadChapterAudio(chapter.id, audioFile)
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

  async function handleDeleteConfirmed() {
    if (!deleteTarget) return
    const chapterId = deleteTarget.id
    setDeleteTarget(null)
    try {
      setError(null)
      await deleteChapter(chapterId)
      await loadChapters()
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to delete chapter.")
    }
  }

  async function handleBatchDelete() {
    setBatchDeleteOpen(false)
    const ids = [...selected]
    setIsDeleting(true)
    const failed: number[] = []
    await Promise.allSettled(ids.map(async (id) => {
      try {
        await deleteChapter(id)
      } catch {
        failed.push(id)
      }
    }))
    setSelected(new Set(failed))
    if (failed.length > 0) {
      setError(`Deleted ${ids.length - failed.length} of ${ids.length} chapters. ${failed.length} failed.`)
    }
    await loadChapters()
    setIsDeleting(false)
  }

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  function toggleSelectAll() {
    setSelected(selected.size === chapters.length ? new Set() : new Set(chapters.map((c) => c.id)))
  }

  return (
    <div className="page app-shell">
      <Breadcrumb items={[
        { label: "Projects", onClick: onBack },
        { label: project?.name ?? `Project ${projectId}` },
      ]} />

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
            {isSaving ? "Saving..." : "Create and Open Chapter"}
          </button>
        </form>
      </CollapsibleSection>

      {error ? <div className="card error" role="alert">{error}</div> : null}

      <CollapsibleSection
        title="Chapters"
        subtitle={`${chapters.length} available`}
        actions={chapters.length > 0 ? (
          <div className="batch-select-actions">
            {selectMode ? (
              <>
                <button type="button" className="batch-btn" onClick={toggleSelectAll}>
                  {selected.size === chapters.length ? "Deselect All" : "Select All"}
                </button>
                <button type="button" className="batch-btn danger" disabled={isDeleting} onClick={() => setBatchDeleteOpen(true)}>
                  {isDeleting ? "Deleting..." : `Delete ${selected.size}`}
                </button>
                <button type="button" className="batch-btn" onClick={() => setSelected(new Set())}>Cancel</button>
              </>
            ) : (
              <button type="button" className="batch-btn" onClick={toggleSelectAll}>Select</button>
            )}
          </div>
        ) : undefined}
      >
        {loading ? <SkeletonListItems count={4} /> : (
          <>
            {chapters.length === 0 ? <p className="muted">No chapters yet. Create one above to begin the review workflow.</p> : null}
            <div className="list">
              {chapters.map((chapter) => {
                const label = `Chapter ${chapter.chapter_number}${chapter.title ? `: ${chapter.title}` : ""}`
                return (
                  <div key={chapter.id} className={`list-item-row${selectMode && selected.has(chapter.id) ? " row-selected" : ""}`}>
                    {selectMode ? (
                      <label className="batch-checkbox" onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" checked={selected.has(chapter.id)} onChange={() => toggleSelect(chapter.id)} />
                      </label>
                    ) : null}
                    <button
                      type="button"
                      className="list-item list-item-grow rich-card"
                      onClick={() => selectMode ? toggleSelect(chapter.id) : onOpenChapter(chapter.id)}
                      aria-label={selectMode ? `Toggle select ${label}` : `Open ${label}`}
                    >
                      <div className="rich-card-top">
                        <span className="rich-card-title">{label}</span>
                        <span className="rich-card-arrow">{selectMode ? "" : "\u203A"}</span>
                      </div>
                      <div className="rich-card-meta">
                        <ChapterStatusBadges chapter={chapter} />
                        {chapter.duration_ms ? (
                          <span className="rich-card-duration">{formatTimecode(chapter.duration_ms)}</span>
                        ) : null}
                      </div>
                    </button>
                    {!selectMode ? (
                      <button type="button" className="danger-button" onClick={() => setDeleteTarget(chapter)}>Delete</button>
                    ) : null}
                  </div>
                )
              })}
            </div>
          </>
        )}
      </CollapsibleSection>
      <ConfirmModal
        open={deleteTarget != null}
        title="Delete Chapter"
        message={`Delete Chapter ${deleteTarget?.chapter_number}${deleteTarget?.title ? `: ${deleteTarget.title}` : ""} and its saved artifacts? This cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        onConfirm={handleDeleteConfirmed}
        onCancel={() => setDeleteTarget(null)}
      />
      <ConfirmModal
        open={batchDeleteOpen}
        title={`Delete ${selected.size} Chapter${selected.size === 1 ? "" : "s"}`}
        message={`Delete ${selected.size} selected chapter${selected.size === 1 ? "" : "s"} and their artifacts? This cannot be undone.`}
        confirmLabel={`Delete ${selected.size}`}
        variant="danger"
        onConfirm={handleBatchDelete}
        onCancel={() => setBatchDeleteOpen(false)}
      />
    </div>
  )
}
