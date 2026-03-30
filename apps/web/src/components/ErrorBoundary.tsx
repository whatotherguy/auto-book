import React from "react"

type ErrorBoundaryProps = {
  children: React.ReactNode
}

type ErrorBoundaryState = {
  error: Error | null
  errorInfo: React.ErrorInfo | null
  showDetails: boolean
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    error: null,
    errorInfo: null,
    showDetails: false
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { error, showDetails: false }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    this.setState({ error, errorInfo })
    console.error("App render error:", error, errorInfo)
  }

  handleReload = () => {
    window.location.reload()
  }

  handleToggleDetails = () => {
    this.setState((currentState) => ({
      showDetails: !currentState.showDetails
    }))
  }

  render() {
    const { error, errorInfo, showDetails } = this.state

    if (!error) {
      return this.props.children
    }

    return (
      <div className="page app-shell">
        <div className="page-hero compact">
          <p className="eyebrow">Application Error</p>
          <h1>Something went wrong</h1>
          <p className="hero-copy">
            The app hit an unexpected render error. Reload the page to try again.
          </p>
        </div>
        <div className="card error error-boundary-card" role="alert">
          <strong>{error.message || "Unknown error"}</strong>
          <div className="row error-boundary-actions">
            <button type="button" onClick={this.handleReload}>
              Reload page
            </button>
            <button type="button" onClick={this.handleToggleDetails} aria-expanded={showDetails}>
              {showDetails ? "Hide details" : "Details"}
            </button>
          </div>
          {showDetails ? (
            <pre className="error-stack">{errorInfo?.componentStack?.trim() || "No component stack available."}</pre>
          ) : null}
        </div>
      </div>
    )
  }
}
