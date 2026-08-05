The history list. Everything JARVIS stored about a session is visible here, and every row can be thrown away.

```jsx
<TurnRow when="04/08/2026, 14:22" question="quanto está vencido com a Jatinox?"
  meta="6 citações · 318 tokens" onOpen={reopen} onDelete={forget} />
```

The delete control is a ghost button that fades in on hover and is always reachable by keyboard. Never confirm with a modal; the row simply goes.
