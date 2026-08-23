import { Component } from 'react'

export default class SceneErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { crashed: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { crashed: true, error }
  }

  render() {
    if (this.state.crashed) {
      return (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-abyss">
          <p className="text-glow text-xl font-bold">3D Renderer Unavailable</p>
          <p className="mt-2 text-xs text-text-muted">
            WebGL context lost — try refreshing.
          </p>
          <button
            onClick={() => this.setState({ crashed: false, error: null })}
            className="glass-panel mt-4 px-4 py-2 text-sm"
          >
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
