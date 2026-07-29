export interface TabsProps {
  tabs: string[];
  active: number;
  onChange: (i: number) => void;
}
