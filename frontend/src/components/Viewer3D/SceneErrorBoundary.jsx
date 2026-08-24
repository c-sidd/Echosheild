import { Component } from 'react'

export default class SceneErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { crashed: false, error: null, generation: 0 }
  }

  static getDerivedStateFromError(error) {
    return { crashed: true, error }
  }

  retry = () => {
    this.setState((state) => ({
      crashed: false,
      error: null,
      generation: state.generation + 1,
    }))
  }

  render() {
    if (this.state.crashed) {
      return (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-abyss">
          <p className="text-glow text-xl font-bold">3D Renderer Unavailable</p>
          <p className="mt-2 text-xs text-text-muted">
            The 3D scene failed to initialize. The renderer can be restarted safely.
          </p>
          <button
            onClick={this.retry}
            className="glass-panel mt-4 px-4 py-2 text-sm"
          >
            Retry
          </button>
        </div>
      )
    }

    return <div key={this.state.generation} className="absolute inset-0">{this.props.children}</div>
  }
}
