Labeled native select — renders a JSON-Schema `enum`/`select` field, also used for theme choice (Light/Dark/System).

```jsx
<SelectField label="Theme" value={theme} onChange={setTheme} options={[{label:"System",value:"system"},{label:"Light",value:"light"},{label:"Dark",value:"dark"}]}/>
```
