export interface NavLink { label: string; icon: string; active?: boolean; onClick?: () => void; }
export interface SideNavProps { links: NavLink[]; }
