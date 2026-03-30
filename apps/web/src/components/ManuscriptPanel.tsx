import { CollapsibleSection } from "./CollapsibleSection"

export function ManuscriptPanel({ text }: { text: string }) {
  return (
    <CollapsibleSection
      title="Manuscript"
      className="manuscript"
      defaultCollapsed={false}
      storageKey="chapter-review:manuscript"
    >
      <pre>{text || "No manuscript text loaded."}</pre>
    </CollapsibleSection>
  )
}
