The bottom of the status panel: what was indexed and which capabilities are actually available.

```jsx
<StatList rows={[["mode","live"],["notes","142"],["links","388"],["model","sonnet-4.6"],["listen","missing"]]} />
```

Always report an absent capability as `missing` rather than omitting the row — the point of the readout is that nothing is swallowed.
