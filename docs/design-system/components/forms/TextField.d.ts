export interface TextFieldProps {
  label: string;
  value: string;
  onChange?: (v: string) => void;
  type?: "text" | "number" | "email" | "password";
  placeholder?: string;
  helpText?: string;
  error?: string;
  disabled?: boolean;
}
