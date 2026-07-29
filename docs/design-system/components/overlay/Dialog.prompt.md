Modal dialog — token creation, replace-secret, note sharing, invite confirmation. One of the two places (with dropdowns/toasts) allowed to use a shadow (`--shadow-overlay`).

```jsx
<Dialog open={open} title="Create API token" onClose={close} footer={<><Button variant="ghost" onClick={close}>Cancel</Button><Button onClick={create}>Create</Button></>}>
  ...form...
</Dialog>
```

200ms overlay transition per motion spec (collapses to 0 under reduced motion).
