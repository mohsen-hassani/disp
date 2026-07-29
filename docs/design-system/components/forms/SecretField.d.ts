export interface SecretFieldProps {
  label: string;
  /** masked placeholder shown when not revealed, e.g. "••••••••1a2b" */
  maskedValue: string;
  helpText?: string;
  onReplace?: () => void;
}
