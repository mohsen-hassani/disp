Generic dashboard tile — modules render into this shell from a manifest, so treat title/icon/items/actions as the full customization surface; don't design bespoke per-module layouts.

```jsx
<TileCard title="Weather" icon="cloud" onRefresh={refetch}>
  <TileItem primary="62°F, cloudy" secondary="Updated 2m ago"/>
</TileCard>
```

`state="loading"` swaps content for static skeleton rows; for error/empty, render `<ErrorView/>`/`<EmptyState/>` as children instead.
