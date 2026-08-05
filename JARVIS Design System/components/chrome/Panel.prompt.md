Use `Panel` for any floating region of the JARVIS interface — it is the only surface treatment in the product, and there are no cards.

```jsx
<Panel side="left" aria-label="Note inspector">
  <PanelHead label="Inspector">
    <Button size="ghost">Close</Button>
  </PanelHead>
  ...
</Panel>
```

`side="left"` and `side="right"` pin the plate to the fixed rails (342px / 268px, 20px gutter, 116px clear at the bottom for the ask bar). `side="free"` gives you the surface with no positioning. Never add a shadow or a larger radius: depth here is translucency + blur + the brighter top border.
