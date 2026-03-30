import { useState } from "react"
import { updateSettings } from "../api"
import { AppSettings } from "../types"
import { CollapsibleSection } from "./CollapsibleSection"
import { Tooltip } from "./Tooltip"

export function SettingsPanel({
  settings,
  onUpdate
}: {
  settings: AppSettings | null
  onUpdate: (next: AppSettings) => void
}) {
  const [openaiKey, setOpenaiKey] = useState("")
  const [anthropicKey, setAnthropicKey] = useState("")
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  async function handleSave() {
    try {
      setIsSaving(true)
      setMessage(null)
      const payload: Record<string, string> = {}
      if (openaiKey) payload.openai_api_key = openaiKey
      if (anthropicKey) payload.anthropic_api_key = anthropicKey
      const next = await updateSettings(payload)
      onUpdate(next)
      setOpenaiKey("")
      setAnthropicKey("")
      setMessage("API keys saved for this session.")
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to save settings.")
    } finally {
      setIsSaving(false)
    }
  }

  async function handleTranscriptionBackendChange(backend: string) {
    try {
      const next = await updateSettings({ transcription_backend: backend })
      onUpdate(next)
    } catch {
      // Ignore -- non-critical
    }
  }

  async function handleLlmProviderChange(provider: string) {
    try {
      const next = await updateSettings({ llm_provider: provider })
      onUpdate(next)
    } catch {
      // Ignore
    }
  }

  return (
    <CollapsibleSection
      title="Settings"
      subtitle={settings?.triage_available ? "AI triage active" : "Configure API keys"}
      defaultCollapsed={true}
      storageKey="chapter-review:settings"
    >
      <div className="settings-panel">
        <div className="settings-row">
          <strong>Transcription engine</strong>
          <Tooltip text="Local uses your CPU/GPU with faster-whisper. Whisper API uses OpenAI's cloud service (requires API key, charges ~$0.006/min).">
            <span className="muted">(?)</span>
          </Tooltip>
        </div>
        <select
          value={settings?.transcription_backend ?? "local"}
          onChange={(e) => void handleTranscriptionBackendChange(e.target.value)}
        >
          <option value="local">Local (faster-whisper){settings?.gpu_available ? " — GPU detected" : ""}</option>
          <option value="whisper_api" disabled={!settings?.has_openai_key}>
            OpenAI Whisper API{settings?.has_openai_key ? "" : " (needs API key)"}
          </option>
        </select>

        <div className="settings-row">
          <strong>AI issue triage</strong>
          <Tooltip text="After detection, sends issues to an LLM to filter likely false positives. Reduces your review queue by ~40%. Requires an API key.">
            <span className="muted">(?)</span>
          </Tooltip>
          {settings?.triage_available ? (
            <span className="settings-status active">Active</span>
          ) : (
            <span className="settings-status inactive">Not configured</span>
          )}
        </div>
        <select
          value={settings?.llm_provider ?? ""}
          onChange={(e) => void handleLlmProviderChange(e.target.value)}
        >
          <option value="">Disabled</option>
          <option value="openai" disabled={!settings?.has_openai_key}>
            OpenAI GPT-4o{settings?.has_openai_key ? "" : " (needs API key)"}
          </option>
          <option value="anthropic" disabled={!settings?.has_anthropic_key}>
            Anthropic Claude{settings?.has_anthropic_key ? "" : " (needs API key)"}
          </option>
        </select>

        <div className="settings-row">
          <strong>API Keys</strong>
          <Tooltip text="Keys are stored in memory only for this session. Add them to .env for persistence across restarts.">
            <span className="muted">(?)</span>
          </Tooltip>
        </div>

        <label>
          OpenAI API Key
          {settings?.has_openai_key ? <span className="settings-status active">Set</span> : <span className="settings-status inactive">Not set</span>}
          <input
            type="password"
            value={openaiKey}
            onChange={(e) => setOpenaiKey(e.target.value)}
            placeholder={settings?.has_openai_key ? "••••••••  (replace)" : "sk-..."}
            autoComplete="off"
          />
        </label>

        <label>
          Anthropic API Key
          {settings?.has_anthropic_key ? <span className="settings-status active">Set</span> : <span className="settings-status inactive">Not set</span>}
          <input
            type="password"
            value={anthropicKey}
            onChange={(e) => setAnthropicKey(e.target.value)}
            placeholder={settings?.has_anthropic_key ? "••••••••  (replace)" : "sk-ant-..."}
            autoComplete="off"
          />
        </label>

        <button type="button" onClick={() => void handleSave()} disabled={isSaving || (!openaiKey && !anthropicKey)}>
          {isSaving ? "Saving..." : "Save API Keys"}
        </button>
        {message ? <p className="muted">{message}</p> : null}
      </div>
    </CollapsibleSection>
  )
}
