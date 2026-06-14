1. Google drive update too slow. - check parallel
2. Google drive upload persist on retry.
3. Vectrola setup - remove frictions.











# long term refactor:
Even Better (Long-Term)

Create:

custom markdown code block
OR
markdown renderer
OR
custom URI scheme

Example:

```vectrola
track: abc123

Plugin renders:
- player UI
- authenticated streaming
- waveform
- caching

Then:
- no JS injection
- no Dataview token access
- much cleaner architecture

This is closest to how polished Obsidian media plugins work.

---

# My Recommendation

## Avoid:
```js id="gdz9we"
window.vectrolaGetAccessToken()
Prefer:
app.plugins.plugins["vectrola-sync"].api.fetchFile(...)

or:

api.streamTrack(id)

where:

plugin internally handles OAuth
token never exposed externally

That is the architecture most likely to survive Obsidian review cleanly.