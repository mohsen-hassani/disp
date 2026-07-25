import { Component, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback: ReactNode | ((error: Error, reset: () => void) => ReactNode);
}

interface ErrorBoundaryState {
  error: Error | null;
}

// Formally M10's file. Pulled forward because §13.8 needs one failing
// tile's *render* to never affect its siblings — same call as M04 made for
// M06's SchemaForm. No telemetry/error-reporting integration (§26 is
// explicit that's out of scope), so `componentDidCatch` intentionally does
// nothing beyond what `getDerivedStateFromError` already captured.
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(): void {
    // No-op — see class doc.
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
