function NotesScreen() {
  const { TextField, Button, Tag, Dialog, IconButton, Icon, EmptyState } = window.DISPDesignSystem_bf3b97;
  const { useState } = React;
  const notes = [
    { id: 1, title: "Router config backup", tags: ["network"], body: "Backup taken 2026-07-20. Config stored at /srv/backups/router-2026-07-20.cfg. Admin password rotated same day — see API tokens for the webhook key used by the rotation script." },
    { id: 2, title: "Guest wifi password", tags: ["network","shared"], body: "SSID: HouseholdGuest. Password rotates monthly, first of the month. Current password shared via the sharing link below — do not text it." },
    { id: 3, title: "Recipe: sourdough starter feed ratio", tags: ["personal"], body: "1:1:1 starter:flour:water by weight, room temp. Feed every 12h in summer, 24h in winter." },
  ];
  const [query, setQuery] = useState("");
  const [activeId, setActiveId] = useState(1);
  const [shareOpen, setShareOpen] = useState(false);
  const filtered = notes.filter(n => n.title.toLowerCase().includes(query.toLowerCase()));
  const active = notes.find(n => n.id === activeId);
  return (
    <div style={{display:"flex",height:"100%"}}>
      <div style={{width:280,borderRight:"1px solid var(--color-border)",display:"flex",flexDirection:"column",padding:16,gap:12}}>
        <div style={{display:"flex",gap:8}}>
          <div style={{flex:1}}><TextField label="" value={query} onChange={setQuery} placeholder="Search notes…"/></div>
          <IconButton label="New note" variant="secondary"><Icon name="plus"/></IconButton>
        </div>
        <div style={{display:"flex",flexDirection:"column",gap:2,overflowY:"auto"}}>
          {filtered.length === 0 ? <EmptyState icon="search" title="No matches" description="Try a different search term."/> : filtered.map(n => (
            <button key={n.id} onClick={() => setActiveId(n.id)} style={{textAlign:"left",border:"none",cursor:"pointer",padding:"10px 10px",borderRadius:8,background:n.id===activeId?"var(--color-surface-sunken)":"transparent"}}>
              <div style={{fontSize:"0.9375rem",fontWeight:500,color:"var(--color-text)"}}>{n.title}</div>
              <div style={{display:"flex",gap:4,marginTop:4}}>{n.tags.map(t=><span key={t} style={{fontSize:11,color:"var(--color-text-muted)",background:"var(--color-surface-raised)",border:"1px solid var(--color-border)",borderRadius:4,padding:"1px 6px"}}>{t}</span>)}</div>
            </button>
          ))}
        </div>
      </div>
      <div style={{flex:1,padding:24,display:"flex",flexDirection:"column",gap:16,maxWidth:"68ch"}}>
        {active && <>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between"}}>
            <h1 style={{fontSize:"1.25rem"}}>{active.title}</h1>
            <div style={{display:"flex",gap:8}}>
              <Button size="sm" variant="secondary" onClick={()=>setShareOpen(true)}>Share</Button>
              <IconButton label="More"><Icon name="more-horizontal"/></IconButton>
            </div>
          </div>
          <div style={{display:"flex",gap:6}}>{active.tags.map(t=><Tag key={t}>{t}</Tag>)}</div>
          <p style={{fontSize:"0.9375rem",lineHeight:1.5,color:"var(--color-text)",margin:0}}>{active.body}</p>
          <div style={{marginTop:"auto",fontSize:"0.75rem",color:"var(--color-text-muted)",display:"flex",gap:14}}>
            <span>⌘K search</span><span>⌘N new</span><span>⌘S share</span>
          </div>
        </>}
      </div>
      <Dialog open={shareOpen} title="Share note" onClose={()=>setShareOpen(false)} footer={<Button onClick={()=>setShareOpen(false)}>Done</Button>}>
        <div style={{display:"flex",flexDirection:"column",gap:10}}>
          <p style={{fontSize:"0.875rem",color:"var(--color-text-muted)",margin:0}}>Anyone with this link and household access can view this note.</p>
          <div style={{display:"flex",gap:8}}>
            <div style={{flex:1,fontFamily:"var(--font-mono)",fontSize:"0.8125rem",padding:"10px 12px",background:"var(--color-surface-sunken)",borderRadius:6,border:"1px solid var(--color-border)",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>https://disp.local/n/8f2a-91c/share</div>
            <Button size="sm" variant="secondary">Copy</Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
window.NotesScreen = NotesScreen;
