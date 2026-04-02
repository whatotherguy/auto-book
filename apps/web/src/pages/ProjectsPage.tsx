import { FormEvent, useEffect, useId, useState } from "react"
import { createProject, deleteProject, getProjects } from "../api"
import { Project } from "../types"
import { CollapsibleSection } from "../components/CollapsibleSection"
import { ConfirmModal } from "../components/ConfirmModal"
import { SkeletonListItems } from "../components/Skeleton"

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return ""
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

export function ProjectsPage({ onOpenProject }: { onOpenProject: (id: number) => void }) {
  const projectNameId = useId()
  const projectNameHelpId = useId()
  const [projects, setProjects] = useState<Project[]>([])
  const [name, setName] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [isDeleting, setIsDeleting] = useState(false)
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false)

  const selectMode = selected.size > 0

  async function load() {
    try {
      setError(null)
      setProjects(await getProjects())
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to load projects.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedName = name.trim()
    if (!trimmedName) return
    try {
      setError(null)
      await createProject(trimmedName)
      setName("")
      await load()
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to create project.")
    }
  }

  async function handleDeleteConfirmed() {
    if (!deleteTarget) return
    const projectId = deleteTarget.id
    setDeleteTarget(null)
    try {
      setError(null)
      await deleteProject(projectId)
      await load()
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to delete project.")
    }
  }

  async function handleBatchDelete() {
    setBatchDeleteOpen(false)
    const ids = [...selected]
    setIsDeleting(true)
    const failed: number[] = []
    await Promise.allSettled(ids.map(async (id) => {
      try {
        await deleteProject(id)
      } catch {
        failed.push(id)
      }
    }))
    setSelected(new Set(failed))
    if (failed.length > 0) {
      setError(`Deleted ${ids.length - failed.length} of ${ids.length} projects. ${failed.length} failed.`)
    }
    await load()
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
    setSelected(selected.size === projects.length ? new Set() : new Set(projects.map((p) => p.id)))
  }

  return (
    <div className="page app-shell">
      <div className="page-hero">
        <p className="eyebrow">Offline Narration Lab</p>
        <h1>Audiobook Editor</h1>
        <p className="hero-copy">
          Review narration like a mastering session, with manuscript context, issue tracking, and waveform-driven decisions in one low-light workspace.
        </p>
      </div>
      <CollapsibleSection
        title="Create Project"
        subtitle="Start a new review workspace for a book or chapter set."
      >
        <form onSubmit={handleCreate}>
          <label htmlFor={projectNameId}>Project name</label>
          <input
            id={projectNameId}
            name="projectName"
            autoComplete="off"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="New project name"
            aria-describedby={projectNameHelpId}
          />
          <p id={projectNameHelpId} className="muted">
            Use one project per title or production batch. You will add chapters, audio, and manuscript text on the next screen.
          </p>
          <button type="submit" disabled={!name.trim()}>
            Create Project
          </button>
        </form>
      </CollapsibleSection>
      {error ? <div className="card error" role="alert">{error}</div> : null}
      <CollapsibleSection
        title="Projects"
        subtitle={`${projects.length} total`}
        actions={projects.length > 0 ? (
          <div className="batch-select-actions">
            {selectMode ? (
              <>
                <button type="button" className="batch-btn" onClick={toggleSelectAll}>
                  {selected.size === projects.length ? "Deselect All" : "Select All"}
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
        {loading ? <SkeletonListItems count={3} /> : (
          <div className="list">
            {projects.length === 0 ? <p className="muted">No projects yet. Create one above to get started.</p> : null}
            {projects.map((project) => (
              <div key={project.id} className={`list-item-row${selectMode && selected.has(project.id) ? " row-selected" : ""}`}>
                {selectMode ? (
                  <label className="batch-checkbox" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={selected.has(project.id)} onChange={() => toggleSelect(project.id)} />
                  </label>
                ) : null}
                <button
                  type="button"
                  className="list-item list-item-grow rich-card"
                  onClick={() => selectMode ? toggleSelect(project.id) : onOpenProject(project.id)}
                  aria-label={selectMode ? `Toggle select ${project.name}` : `Open project ${project.name}`}
                >
                  <div className="rich-card-top">
                    <span className="rich-card-title">{project.name}</span>
                    <span className="rich-card-arrow">{selectMode ? "" : "\u203A"}</span>
                  </div>
                  <div className="rich-card-meta">
                    <span className="rich-card-badge">{project.chapter_count ?? 0} chapter{project.chapter_count === 1 ? "" : "s"}</span>
                    {project.updated_at ? (
                      <span className="rich-card-time">Updated {relativeTime(project.updated_at)}</span>
                    ) : null}
                  </div>
                </button>
                {!selectMode ? (
                  <button type="button" className="danger-button" onClick={() => setDeleteTarget(project)}>Delete</button>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </CollapsibleSection>
      <ConfirmModal
        open={deleteTarget != null}
        title="Delete Project"
        message={`Delete "${deleteTarget?.name}" and all its chapters? This cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        onConfirm={handleDeleteConfirmed}
        onCancel={() => setDeleteTarget(null)}
      />
      <ConfirmModal
        open={batchDeleteOpen}
        title={`Delete ${selected.size} Project${selected.size === 1 ? "" : "s"}`}
        message={`Delete ${selected.size} selected project${selected.size === 1 ? "" : "s"} and all their chapters? This cannot be undone.`}
        confirmLabel={`Delete ${selected.size}`}
        variant="danger"
        onConfirm={handleBatchDelete}
        onCancel={() => setBatchDeleteOpen(false)}
      />
    </div>
  )
}
