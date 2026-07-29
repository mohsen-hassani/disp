function AccountScreen() {
  const { Tabs, TextField, SelectField, SecretField, Switch, Button, Dialog, Badge, IconButton, Icon } = window.DISPDesignSystem_bf3b97;
  const { useState } = React;
  const [tab, setTab] = useState(0);
  const [name, setName] = useState("Jordan Lee");
  const [theme, setTheme] = useState("system");
  const [createOpen, setCreateOpen] = useState(false);
  const [revealStep, setRevealStep] = useState(false);
  const [tokenName, setTokenName] = useState("");

  const tokens = [
    { name: "Home Assistant webhook", created: "2026-06-02", last: "2h ago" },
    { name: "Backup script", created: "2026-04-11", last: "3d ago" },
  ];
  const invites = [
    { email: "sam@household.example", status: "pending" },
    { email: "kai@household.example", status: "accepted" },
    { email: "old-invite@household.example", status: "expired" },
  ];

  return (
    <div style={{padding:24,maxWidth:720,display:"flex",flexDirection:"column",gap:20}}>
      <h1 style={{fontSize:"1.5rem"}}>Account</h1>
      <Tabs tabs={["Details","API tokens","Invites"]} active={tab} onChange={setTab}/>
      {tab === 0 && (
        <div style={{display:"flex",flexDirection:"column",gap:16,maxWidth:420}}>
          <TextField label="Display name" value={name} onChange={setName}/>
          <TextField label="Email" value="jordan@household.example" disabled/>
          <SelectField label="Theme" value={theme} onChange={setTheme} options={[{label:"System",value:"system"},{label:"Light",value:"light"},{label:"Dark",value:"dark"}]}/>
          <Switch checked={true} onChange={()=>{}} label="Show offline banner when disconnected"/>
          <div><Button size="sm">Save changes</Button></div>
        </div>
      )}
      {tab === 1 && (
        <div style={{display:"flex",flexDirection:"column",gap:12}}>
          <div style={{display:"flex",justifyContent:"flex-end"}}><Button size="sm" onClick={()=>{setCreateOpen(true);setRevealStep(false);setTokenName("");}}>Create token</Button></div>
          {tokens.map(t => (
            <div key={t.name} style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"12px 14px",border:"1px solid var(--color-border)",borderRadius:10,background:"var(--color-surface-raised)"}}>
              <div>
                <div style={{fontWeight:500,fontSize:"0.9375rem"}}>{t.name}</div>
                <div style={{fontSize:"0.75rem",color:"var(--color-text-muted)"}}>Created {t.created} · last used {t.last}</div>
              </div>
              <IconButton label="Revoke" variant="secondary"><Icon name="trash-2"/></IconButton>
            </div>
          ))}
          <Dialog open={createOpen} title="Create API token" onClose={()=>setCreateOpen(false)} footer={
            revealStep
              ? <Button onClick={()=>setCreateOpen(false)}>I've saved it</Button>
              : <><Button variant="ghost" onClick={()=>setCreateOpen(false)}>Cancel</Button><Button onClick={()=>setRevealStep(true)} disabled={!tokenName}>Create</Button></>
          }>
            {!revealStep ? (
              <TextField label="Token name" value={tokenName} onChange={setTokenName} placeholder="e.g. Backup script"/>
            ) : (
              <div style={{display:"flex",flexDirection:"column",gap:10}}>
                <div style={{display:"flex",gap:8,alignItems:"center",padding:8,background:"color-mix(in oklch, var(--color-warning) 12%, var(--color-surface-raised))",borderRadius:8}}>
                  <Icon name="triangle-alert" size={16}/>
                  <span style={{fontSize:"0.8125rem"}}>This is shown once. Copy it now — it can't be retrieved again.</span>
                </div>
                <div style={{display:"flex",gap:8}}>
                  <div style={{flex:1,fontFamily:"var(--font-mono)",fontSize:"0.8125rem",padding:"10px 12px",background:"var(--color-surface-sunken)",borderRadius:6,border:"1px solid var(--color-border)",overflow:"hidden"}}>disp_live_9f2a7c3e1b8d4f0a</div>
                  <Button size="sm" variant="secondary">Copy</Button>
                </div>
              </div>
            )}
          </Dialog>
        </div>
      )}
      {tab === 2 && (
        <div style={{display:"flex",flexDirection:"column",gap:8}}>
          {invites.map(i => (
            <div key={i.email} style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"10px 14px",border:"1px solid var(--color-border)",borderRadius:10}}>
              <span style={{fontSize:"0.9375rem"}}>{i.email}</span>
              <Badge tone={i.status==="accepted"?"success":i.status==="expired"?"danger":"neutral"}>{i.status}</Badge>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
window.AccountScreen = AccountScreen;
