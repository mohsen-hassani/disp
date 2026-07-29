Transient notification. Position it bottom-center on mobile, bottom-right (above the bottom nav) on desktop — the component itself doesn't position; the app shell stacks a toast region.

```jsx
<Toast tone="success" message="Note saved" />
<Toast message="Update available" actionLabel="Reload" onAction={reload}/>
```
