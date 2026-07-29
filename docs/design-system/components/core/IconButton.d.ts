import { ReactNode } from "react";
export interface IconButtonProps {
  children: ReactNode;
  label: string;
  variant?: "ghost" | "secondary";
  size?: "sm" | "md";
  onClick?: () => void;
}
