function DashboardScreen() {
  const { TileCard, TileItem, Badge, Button, EmptyState, ErrorView } = window.DISPDesignSystem_bf3b97;
  const { useState } = React;
  const [refreshedAt, setRefreshedAt] = useState("2m ago");
  return (
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill, minmax(260px, 1fr))",gap:16,padding:20}}>
      <TileCard title="Uptime monitor" icon="activity" onRefresh={()=>setRefreshedAt("just now")}>
        <TileItem primary="api.home.local" secondary={`Updated ${refreshedAt}`} badge={<Badge tone="success">Up</Badge>}/>
        <TileItem primary="nas.home.local" secondary="99.2% / 30d" badge={<Badge tone="danger">Down</Badge>}/>
        <TileItem primary="printer.home.local" secondary="99.9% / 30d" badge={<Badge tone="success">Up</Badge>}/>
      </TileCard>
      <TileCard title="Notes" icon="file-text" onRefresh={()=>{}} actions={<Button size="sm" variant="secondary">Open Notes</Button>}>
        <TileItem primary="Router config backup" secondary="Edited yesterday"/>
        <TileItem primary="Guest wifi password" secondary="Edited 4d ago"/>
      </TileCard>
      <TileCard title="Backups" icon="database" state="loading" onRefresh={()=>{}}/>
      <TileCard title="Weather" icon="cloud" onRefresh={()=>{}}>
        <TileItem primary="61°F, overcast" secondary="Updated 12m ago"/>
      </TileCard>
      <TileCard title="Storage" icon="hard-drive">
        <EmptyState icon="hard-drive" title="No devices configured" description="Add a device to see storage usage here."/>
      </TileCard>
      <TileCard title="Calendar" icon="calendar" onRefresh={()=>{}}>
        <ErrorView message="Couldn't reach calendar source." onRetry={()=>{}}/>
      </TileCard>
    </div>
  );
}
window.DashboardScreen = DashboardScreen;
