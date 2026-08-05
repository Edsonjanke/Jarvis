The instant search list, shown while typing and replaced by the answer on Enter.

```jsx
<ResultRow type="note" title="Deposit policy" where="demo/notes/deposit-policy.md"
  snippet="Half up front, the rest on handover." onClick={open} />
```

When nothing matches, render one row of snippet text instead: `No file matches "…".` Do not show an empty state illustration — there are none in this product.
