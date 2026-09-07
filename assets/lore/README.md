# Optional lore packs

Place `.json` files here to extend the offline lore retriever. Each file is a
dictionary keyed by exact world name; each value is a list of entries:

```json
{
  "Naruto": [
    {
      "title": "Medical ninjutsu",
      "keys": "medical ninjutsu healing chakra scalpel training",
      "text": "A concise, source-conscious lore note and its prerequisites."
    }
  ]
}
```

Keep notes concise. Official source material should outrank wiki summaries;
forum theories should be identified as uncertain rather than stated as canon.
