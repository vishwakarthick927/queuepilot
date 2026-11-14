import { Component, type ReactNode } from 'react'

// If one panel crashes, show a small notice instead of blanking the whole dashboard.
export class Guard extends Component<{ name: string; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="num border border-alert/40 bg-alert/5 px-5 py-4 text-xs text-alert">
        {this.props.name} panel failed to render. The rest of the dashboard still works; reload to retry.
      </div>
    )
  }
}
