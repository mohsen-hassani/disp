function AppShell({ screen, setScreen, children }) {
  const { TopBar, SideNav, BottomNav, IconButton, Icon, Avatar, Menu, OfflineBanner } = window.DISPDesignSystem_bf3b97;
  const { useState } = React;
  const [menuOpen, setMenuOpen] = useState(false);
  const [offline, setOffline] = useState(false);
  const links = [
    { label: "Dashboard", icon: "layout-grid", active: screen === "dashboard", onClick: () => setScreen("dashboard") },
    { label: "Notes", icon: "file-text", active: screen === "notes", onClick: () => setScreen("notes") },
    { label: "Account", icon: "user", active: screen === "account", onClick: () => setScreen("account") },
  ];
  return (
    <div style={{height:"100%",display:"flex",flexDirection:"column"}}>
      {offline && <OfflineBanner showingSavedData/>}
      <TopBar userMenu={
        <div style={{position:"relative"}}>
          <IconButton label="User menu" onClick={()=>setMenuOpen(o=>!o)}><Avatar name="Jordan Lee" size={28}/></IconButton>
          <Menu open={menuOpen} onClose={()=>setMenuOpen(false)} items={[
            { label: "Account", icon: "user", onClick: () => setScreen("account") },
            { label: "API tokens", icon: "key", onClick: () => setScreen("account") },
            { label: "Toggle offline demo", icon: "wifi-off", onClick: () => setOffline(o=>!o) },
            { label: "Sign out", icon: "log-out", danger: true, onClick: () => setScreen("login") },
          ]}/>
        </div>
      }/>
      <div style={{flex:1,display:"flex",minHeight:0}}>
        <SideNav links={links}/>
        <div style={{flex:1,overflowY:"auto"}}>{children}</div>
      </div>
      <div className="mobile-only" style={{display:"none"}}><BottomNav links={links}/></div>
    </div>
  );
}

function App() {
  const { useState, useEffect } = React;
  const [route, setRoute] = useState("login");
  const [screen, setScreen] = useState("dashboard");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", "system");
  }, []);

  if (route === "login") return <LoginScreen onLogin={() => setRoute("app")}/>;
  if (route === "invite") return <InviteScreen state="pending" onAccept={() => setRoute("app")}/>;
  if (route === "invite-expired") return <InviteScreen state="expired"/>;

  const screens = { dashboard: <DashboardScreen/>, notes: <NotesScreen/>, account: <AccountScreen/> };
  return (
    <AppShell screen={screen} setScreen={setScreen}>
      {screens[screen]}
      <div style={{position:"fixed",bottom:12,left:12,display:"flex",gap:6,zIndex:100}}>
        <button onClick={()=>setRoute("login")} style={{fontSize:11,padding:"4px 8px",borderRadius:6,border:"1px solid var(--color-border)",background:"var(--color-surface-raised)",color:"var(--color-text-muted)",cursor:"pointer"}}>view: login</button>
        <button onClick={()=>setRoute("invite")} style={{fontSize:11,padding:"4px 8px",borderRadius:6,border:"1px solid var(--color-border)",background:"var(--color-surface-raised)",color:"var(--color-text-muted)",cursor:"pointer"}}>view: invite</button>
        <button onClick={()=>setRoute("invite-expired")} style={{fontSize:11,padding:"4px 8px",borderRadius:6,border:"1px solid var(--color-border)",background:"var(--color-surface-raised)",color:"var(--color-text-muted)",cursor:"pointer"}}>view: invite expired</button>
      </div>
    </AppShell>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
