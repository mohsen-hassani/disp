import { ReactNode } from "react";
export interface TileItemProps {
  primary: string;
  secondary?: string;
  badge?: ReactNode;
}
export interface TileCardProps {
  title: string;
  icon: string;
  children: ReactNode;
  actions?: ReactNode;
  onRefresh?: () => void;
  state?: "default" | "loading" | "error" | "empty";
}
