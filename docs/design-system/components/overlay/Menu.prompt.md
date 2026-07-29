Dropdown menu — the top-bar user menu (Account/Tokens/Theme/Sign out) and note row overflow actions.

```jsx
<Menu open={open} onClose={close} items={[{label:"Account",icon:"user",onClick:goAccount},{label:"Sign out",icon:"log-out",danger:true,onClick:signOut}]}/>
```

Render inside a `position:relative` trigger wrapper — the menu anchors to it.
