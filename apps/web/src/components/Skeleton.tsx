export function SkeletonLine({ width = "100%" }: { width?: string }) {
  return <div className="skeleton-line" style={{ width }} />
}

export function SkeletonIssueCard() {
  return (
    <div className="skeleton-card">
      <div className="skeleton-card-row">
        <SkeletonLine width="80px" />
        <SkeletonLine width="100px" />
        <SkeletonLine width="60px" />
      </div>
      <SkeletonLine width="90%" />
      <SkeletonLine width="70%" />
    </div>
  )
}

export function SkeletonIssueList({ count = 5 }: { count?: number }) {
  return (
    <div className="skeleton-list">
      {Array.from({ length: count }, (_, i) => (
        <SkeletonIssueCard key={i} />
      ))}
    </div>
  )
}

export function SkeletonTimeline() {
  return (
    <div className="skeleton-timeline">
      <div className="skeleton-timeline-ruler">
        <SkeletonLine width="40px" />
        <SkeletonLine width="40px" />
        <SkeletonLine width="40px" />
      </div>
      <div className="skeleton-timeline-lane" />
    </div>
  )
}
