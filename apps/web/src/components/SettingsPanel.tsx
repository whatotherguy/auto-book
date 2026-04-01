import { useEffect, useState } from "react"
import { getGpuStatus, updateSettings } from "../api"
import { AppSettings } from "../types"
import { CollapsibleSection } from "./CollapsibleSection"
import { Tooltip } from "./Tooltip"

function GpuThermalBadge({ tempC }: { tempC: number | null }) {
  if (tempC == null) return null
  let cls = "gpu-temp-badge"
  if (tempC >= 85) cls += " critical"
  else if (tempC >= 78) cls += " warning"
  else cls += " ok"
  return <span className={cls}>{tempC}°C</span>
}

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
  const [liveTemp, setLiveTemp] = useState<number | null>(settings?.gpu_thermal?.temperature_c ?? null)

  // Poll GPU temperature while panel is visible and GPU monitoring is available
  useEffect(() => {
    if (!settings?.gpu_thermal?.monitoring_available) return
    let cancelled = false
    const poll = async () => {
      try {
        const status = await getGpuStatus()
        if (!cancelled) setLiveTemp(status.temperature_c)
      } catch { /* ignore */ }
    }
    poll()
    const interval = setInterval(poll, 10_000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [settings?.gpu_thermal?.monitoring_available])

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

  async function handleThermalProtectionToggle(enabled: boolean) {
    try {
      const next = await updateSettings({ gpu_thermal_protection: enabled })
      onUpdate(next)
    } catch { /* ignore */ }
  }

  async function handleThermalSettingChange(key: string, value: number) {
    try {
      const next = await updateSettings({ [key]: value })
      onUpdate(next)
    } catch { /* ignore */ }
  }

  const thermalAvailable = settings?.gpu_thermal?.monitoring_available ?? false
  const thermalEnabled = settings?.thermal_protection?.enabled ?? true

  return (
    <CollapsibleSection
      title="Settings"
      subtitle={settings?.triage_available ? "AI triage active" : "Configure API keys"}
      defaultCollapsed={true}
      storageKey="chapter-review:settings"
    >
      <div className="settings-panel">
        {/* --- Transcription Engine --- */}
        <div className="settings-row">
          <strong>Transcription engine</strong>
          <Tooltip text="Local uses your CPU/GPU with faster-whisper. Whisper API uses OpenAI's cloud service (requires API key, charges ~$0.006/min). Use the API to avoid GPU heat and get faster results on long files.">
            <span className="muted">(?)</span>
          </Tooltip>
        </div>
        <select
          value={settings?.transcription_backend ?? "local"}
          onChange={(e) => void handleTranscriptionBackendChange(e.target.value)}
        >
          <option value="local">
            Local (faster-whisper){settings?.gpu_available ? ` — ${settings.gpu_name ?? "GPU"}` : " — CPU only"}
          </option>
          <option value="whisper_api" disabled={!settings?.has_openai_key}>
            OpenAI Whisper API (cloud){settings?.has_openai_key ? " — no GPU needed" : " (needs API key)"}
          </option>
        </select>
        {settings?.transcription_backend === "local" && settings?.gpu_available && (
          <p className="muted settings-hint">
            {settings.gpu_name} ({settings.gpu_vram_gb ?? "?"}GB VRAM)
            {liveTemp != null && <> — <GpuThermalBadge tempC={liveTemp} /></>}
          </p>
        )}
        {settings?.transcription_backend === "local" && !settings?.gpu_available && (
          <p className="muted settings-hint" style={{ color: "var(--color-warning, #e6a817)" }}>
            No GPU detected. Local transcription will run on CPU (slow). Consider using the Whisper API for faster results.
          </p>
        )}

        {/* --- GPU Thermal Protection --- */}
        {settings?.gpu_available && settings?.transcription_backend === "local" && (
          <>
            <div className="settings-row" style={{ marginTop: 12 }}>
              <strong>GPU thermal protection</strong>
              <Tooltip text="Monitors GPU temperature during transcription. Pauses processing if the GPU gets too hot, preventing thermal shutdown. Recommended for laptops and smaller cases.">
                <span className="muted">(?)</span>
              </Tooltip>
              {thermalAvailable ? (
                <span className={`settings-status ${thermalEnabled ? "active" : "inactive"}`}>
                  {thermalEnabled ? "Active" : "Off"}
                </span>
              ) : (
                <span className="settings-status inactive">nvidia-smi not found</span>
              )}
            </div>
            <label className="settings-checkbox">
              <input
                type="checkbox"
                checked={thermalEnabled}
                onChange={(e) => void handleThermalProtectionToggle(e.target.checked)}
                disabled={!thermalAvailable}
              />
              Pause transcription when GPU overheats
            </label>
            {thermalEnabled && thermalAvailable && (
              <div className="thermal-settings-grid">
                <label>
                  Warning temp
                  <Tooltip text="GPU temperature at which transcription briefly throttles (short pauses between segments).">
                    <span className="muted">(?)</span>
                  </Tooltip>
                  <div className="thermal-input-row">
                    <input
                      type="number"
                      min={60}
                      max={90}
                      value={settings?.thermal_protection?.warning_temp_c ?? 78}
                      onChange={(e) => void handleThermalSettingChange("gpu_temp_warning", Number(e.target.value))}
                    />
                    <span>°C</span>
                  </div>
                </label>
                <label>
                  Critical temp
                  <Tooltip text="GPU temperature at which transcription fully pauses for cooldown. Should be below your GPU's throttle point (typically 83-90°C for RTX 4070).">
                    <span className="muted">(?)</span>
                  </Tooltip>
                  <div className="thermal-input-row">
                    <input
                      type="number"
                      min={70}
                      max={95}
                      value={settings?.thermal_protection?.critical_temp_c ?? 85}
                      onChange={(e) => void handleThermalSettingChange("gpu_temp_critical", Number(e.target.value))}
                    />
                    <span>°C</span>
                  </div>
                </label>
                <label>
                  Cooldown pause
                  <Tooltip text="How long to pause (in seconds) when the GPU hits critical temperature. The system resumes early if the GPU cools below the warning threshold.">
                    <span className="muted">(?)</span>
                  </Tooltip>
                  <div className="thermal-input-row">
                    <input
                      type="number"
                      min={10}
                      max={120}
                      step={5}
                      value={settings?.thermal_protection?.cooldown_seconds ?? 30}
                      onChange={(e) => void handleThermalSettingChange("gpu_cooldown_seconds", Number(e.target.value))}
                    />
                    <span>sec</span>
                  </div>
                </label>
              </div>
            )}
          </>
        )}

        {/* --- AI Issue Triage --- */}
        <div className="settings-row" style={{ marginTop: 12 }}>
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

        {/* --- API Keys --- */}
        <div className="settings-row" style={{ marginTop: 12 }}>
          <strong>API Keys</strong>
          <Tooltip text="Keys are stored in memory only for this session. Add them to .env for persistence across restarts. An OpenAI key enables both Whisper API transcription and GPT triage.">
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
