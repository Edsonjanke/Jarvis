Sits in the ask bar's action row while a thread is live, and is absent otherwise.

```jsx
{thread ? <ThreadBar onNew={newThread} /> : null}
```

It is the one place a soft accent fill is used behind text outside a pressed button — it is state, not decoration.
