Schema `secret` field — always masked, never echoes real plaintext. "Reveal" only toggles the masked display; changing the value requires Replace.

```jsx
<SecretField label="Webhook signing key" maskedValue="••••••••••••9f2a" onReplace={openReplaceDialog}/>
```
