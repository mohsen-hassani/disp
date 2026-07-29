export interface ErrorViewProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  fullPage?: boolean;
}
