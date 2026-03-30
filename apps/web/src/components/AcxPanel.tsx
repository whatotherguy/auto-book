import { AcxCheck } from "../types"
import { CollapsibleSection } from "./CollapsibleSection"

export function AcxPanel({
  report,
  onRun,
  disabled,
  isRunning = false
}: {
  report: AcxCheck | null
  onRun: () => void
  disabled?: boolean
  isRunning?: boolean
}) {
  return (
    <CollapsibleSection
      title="ACX Preflight"
      subtitle={isRunning ? "Running…" : report ? (report.passes_acx ? "Pass" : "Needs Work") : "Not Run Yet"}
      defaultCollapsed={true}
      storageKey="chapter-review:acx"
      actions={
        <button
          type="button"
          onClick={onRun}
          disabled={disabled || isRunning}
          aria-busy={isRunning}
          className={isRunning ? "button-busy" : undefined}
        >
          {isRunning ? (
            <>
              <span className="button-spinner" aria-hidden="true" />
              Running ACX…
            </>
          ) : (
            "Run ACX Check"
          )}
        </button>
      }
    >

      {!report ? <p className="muted">Run this to get a loudness, noise, and clipping readout before mastering.</p> : null}

      {report ? (
        <>
          <p><strong>Status:</strong> {report.passes_acx ? "Pass" : "Needs work"}</p>
          <p>
            <strong>Levels:</strong> RMS {report.levels.rms_dbfs} dBFS, Peak {report.levels.peak_dbfs} dBFS,
            Noise Floor {report.levels.estimated_noise_floor_dbfs ?? "n/a"} dBFS
          </p>
          <p className="muted">{report.levels.noise_floor_note}</p>
          <p>
            <strong>Format:</strong> {report.format.container.toUpperCase()}, {report.format.sample_rate_hz} Hz,
            {report.format.channels} ch, {report.format.bit_depth}-bit
          </p>
          <div className="list">
            {report.checks.map((check) => (
              <div key={check.name} className="list-item static-item">
                <strong>{check.name}</strong> | {check.status}
                <div>{check.actual} vs {check.target}</div>
                <div className="muted">{check.summary}</div>
                {check.suggestion ? <div>{check.suggestion}</div> : null}
              </div>
            ))}
          </div>
          {report.fix_suggestions.length ? (
            <>
              <h4>Suggested Fixes</h4>
              <div className="list">
                {report.fix_suggestions.map((suggestion) => (
                  <div key={suggestion} className="list-item static-item">{suggestion}</div>
                ))}
              </div>
            </>
          ) : null}
          <div className="list">
            {report.notes.map((note) => (
              <div key={note} className="list-item static-item muted">{note}</div>
            ))}
          </div>
        </>
      ) : null}
    </CollapsibleSection>
  )
}
