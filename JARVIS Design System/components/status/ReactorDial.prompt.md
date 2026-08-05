Sits at the top of the status panel and is the only place the product reports what it is doing right now.

```jsx
<ReactorDial state="listening" level={0.4} sub={'diga "jarvis"'} />
```

It runs on a 33ms timer rather than requestAnimationFrame, so it keeps reading in a backgrounded tab. State words are lower case and never punctuated. Do not add a spinner, a progress bar or a percentage anywhere else — this dial is the product's entire loading vocabulary.
