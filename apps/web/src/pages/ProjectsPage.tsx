import { FormEvent, useEffect, useId, useState } from "react"
import { createProject, deleteProject, getProjects } from "../api"
import { Project } from "../types"
import { CollapsibleSection } from "../components/CollapsibleSection"

export function ProjectsPage({ onOpenProject }: { onOpenProject: (id: number) => void }) {
  const projectNameId = useId()
  const projectNameHelpId = useId()
  const [projects, setProjects] = useState<Project[]>([])
  const [name, setName] = useState("")
  const [error, setError] = useState<string | null>(null)

  async function load() {
    try {
      setError(null)
      setProjects(await getProjects())
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to load projects.")
    }
  }

  useEffect(() => {
    load()
  }, [])

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

  async function handleDelete(projectId: number) {
    if (!window.confirm("Delete this project and all its chapters?")) {
      return
    }

    try {
      setError(null)
      await deleteProject(projectId)
      await load()
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to delete project.")
    }
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
      <CollapsibleSection title="Projects" subtitle={`${projects.length} total`}>
        <div className="list">
          {projects.map((project) => (
            <div key={project.id} className="list-item-row">
              <button
                type="button"
                className="list-item list-item-grow"
                onClick={() => onOpenProject(project.id)}
                aria-label={`Open project ${project.name}`}
              >
                {project.name}
              </button>
              <button type="button" className="danger-button" onClick={() => handleDelete(project.id)}>
                Delete
              </button>
            </div>
          ))}
        </div>
      </CollapsibleSection>
    </div>
  )
}
