function AuthLayout({ children }) {
  return (
    <div style={{height:"100%",display:"flex",alignItems:"center",justifyContent:"center",background:"var(--color-surface)"}}>
      <div style={{width:360,display:"flex",flexDirection:"column",gap:24}}>
        <div style={{fontWeight:700,fontSize:"1.25rem",letterSpacing:"-0.01em"}}>DISP</div>
        {children}
      </div>
    </div>
  );
}

function LoginScreen({ onLogin }) {
  const { TextField, Button } = window.DISPDesignSystem_bf3b97;
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  return (
    <AuthLayout>
      <div style={{display:"flex",flexDirection:"column",gap:4}}>
        <h1 style={{fontSize:"1.25rem"}}>Sign in</h1>
        <p style={{fontSize:"0.875rem",color:"var(--color-text-muted)",margin:0}}>Contact your admin if you don't have an account or need a password reset.</p>
      </div>
      <div style={{display:"flex",flexDirection:"column",gap:14}}>
        <TextField label="Email" type="email" value={email} onChange={setEmail} placeholder="you@example.com"/>
        <TextField label="Password" type="password" value={password} onChange={setPassword}/>
      </div>
      <Button onClick={onLogin}>Sign in</Button>
    </AuthLayout>
  );
}

function InviteScreen({ state, onAccept }) {
  const { TextField, Button, Icon } = window.DISPDesignSystem_bf3b97;
  const { useState } = React;
  const [password, setPassword] = useState("");
  if (state === "expired" || state === "used" || state === "not-found") {
    const copy = {
      expired: ["Invite expired", "This invite link is no longer valid. Ask your admin to send a new one."],
      used: ["Invite already used", "This invite has already been accepted. Sign in instead."],
      "not-found": ["Invite not found", "Check the link your admin sent — it may have been mistyped."],
    }[state];
    return (
      <AuthLayout>
        <div style={{display:"flex",flexDirection:"column",alignItems:"flex-start",gap:8}}>
          <span style={{width:40,height:40,borderRadius:10,background:"color-mix(in oklch, var(--color-danger) 14%, var(--color-surface-raised))",color:"var(--color-danger)",display:"flex",alignItems:"center",justifyContent:"center"}}><Icon name="triangle-alert" size={20}/></span>
          <h1 style={{fontSize:"1.125rem"}}>{copy[0]}</h1>
          <p style={{fontSize:"0.875rem",color:"var(--color-text-muted)",margin:0}}>{copy[1]}</p>
        </div>
      </AuthLayout>
    );
  }
  return (
    <AuthLayout>
      <div style={{display:"flex",flexDirection:"column",gap:4}}>
        <h1 style={{fontSize:"1.25rem"}}>Accept invite</h1>
        <p style={{fontSize:"0.875rem",color:"var(--color-text-muted)",margin:0}}>jordan@household.example — set a password to finish.</p>
      </div>
      <TextField label="Password" type="password" value={password} onChange={setPassword}/>
      <Button onClick={onAccept}>Create account</Button>
    </AuthLayout>
  );
}

Object.assign(window, { LoginScreen, InviteScreen });
