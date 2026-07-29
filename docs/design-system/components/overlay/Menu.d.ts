export interface MenuItem {
  label: string;
  icon?: string;
  onClick?: () => void;
  danger?: boolean;
  submenu?: MenuItem[];
}
export interface MenuProps {
  open: boolean;
  items: MenuItem[];
  onClose: () => void;
  align?: "left" | "right";
}
