Every picker in the status panel — Cérebro, Ferramentas, Habilidades, Alterações — is a list of these.

```jsx
<BrainRow name="Sonnet 4.6" note="rápido, o padrão" pressed onClick={switchBrain} />
<BrainRow name="Google Drive" note="falta GOOGLE_OAUTH_TOKEN" disabled />
<BrainRow name="Cobrança" note="cobrar fornecedor, boleto vencido, atraso…" />
```

The note is not optional in practice: a row whose state you cannot explain should not be on screen. Selection is the inset accent edge, never a checkmark.
