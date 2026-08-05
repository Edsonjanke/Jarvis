The live log in the bottom of the right rail — timestamp, channel tag, line.

```jsx
<TerminalLog busy={thinking} height={140} lines={[
  { at: "22:37:02", tag: "sys",  text: "índice aberto — 44 notas" },
  { at: "22:37:41", tag: "info", text: "consulta: quanto está vencido com a Jatinox?" },
  { at: "22:37:45", tag: "ok",   text: "resposta pronta · 6 citações · 4,1s" },
]}></TerminalLog>
```

Follow the product's rule about copy: the log states what happened, never that things are fine. `err` and `warn` lines must name the fix. Requires the `hud-caret` keyframes (in `tokens/base.css`).
