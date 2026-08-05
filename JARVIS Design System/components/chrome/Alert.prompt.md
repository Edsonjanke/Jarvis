The only interruption in the product — stack these at the top of the viewport, and show none at all when things work.

```jsx
<div role="status" aria-live="polite" style={{position:"fixed",zIndex:8,top:0,left:0,right:0}}>
  <Alert level="crit" label="Offline">The JARVIS server is not answering.</Alert>
  <Alert level="warn" label="Skipped">3 files were not indexed. unreadable PDF; over the size limit</Alert>
</div>
```

Never write a success alert, and never soften the copy: "Nothing was indexed. That is a failure, not an empty result." is the register.
