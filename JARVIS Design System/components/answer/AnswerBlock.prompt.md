The result of a question — it opens above the ask field, never in a modal.

```jsx
<AnswerBlock kind="ask" meta="sonnet-4.6 · read 14 notes · 2 remembered · 4.1s" body={text}>
  <Eyebrow>Sources</Eyebrow>
  {cites.map((c) => <Cite key={c.id} type={c.type} title={c.title} onClick={() => open(c.id)} />)}
</AnswerBlock>
```

The meta line is the receipt: which model, how many notes were read, whether memory or a skill shaped it, how long it took. Do not shorten it, and do not move it below the answer.
