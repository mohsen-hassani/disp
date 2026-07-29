export interface ToastProps {
  message: string;
  tone?: "neutral" | "success" | "danger";
  actionLabel?: string;
  onAction?: () => void;
  onDismiss?: () => void;
}
