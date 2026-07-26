import { Component, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback: ReactNode | ((error: Error, reset: () => void) => ReactNode);
}

interface ErrorBoundaryState {
  error: Error | null;
}

// §20.2: three of these are wired up (root, route, tile) — no
// telemetry/error-reporting integration (§1.2 is explicit that's out of
// scope), but a boundary MUST still log the caught error to `console.error`
// so it isn't silently swallowed for someone debugging locally.
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error): void {
    console.error(error);
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (error) {
      return typeof this.props.fallback === 'function'
        ? this.props.fallback(error, this.reset)
        : this.props.fallback;
    }
    return this.props.children;
  }
}
