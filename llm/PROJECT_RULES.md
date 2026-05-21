# Project Rules

This file is the durable implementation context for `Plex Music Player`.

## Product Goal

Build a local desktop Plex music player with a classic standalone-player UX.

Core product constraints:

- Cross-platform first: macOS and Linux are required.
- Base UI stack: `PySide6` with Qt Widgets.
- Playback must use a native backend, not Python audio decoding for the main audio path.
- The final app must be distributable as a self-contained desktop bundle.
- Architecture must stay explicit, testable, and easy to extend.

## Non-Goals

- No embedded browser shell.
- No attempt at full Plex ecosystem coverage.
- No compatibility layer for legacy provider behavior.
- No provider telemetry/scrobbling feature in the current product.
- No plugin system, downloads, lyrics, or DSP chain in the current product.

## Mandatory Technology Choices

- UI: `PySide6`
- Playback backend: `libmpv` through Python bindings
- Provider integration: `plexapi` plus small local Plex-specific adapters where needed
- Runtime architecture: layered application code under `src/app`

## Layer Boundaries

Use these layers:

- `domain`: entities, value objects, protocols, contracts
- `application`: orchestration of auth, search, library, queue, playback, settings
- `infrastructure`: Plex API, playback engine, persistence, cache, logging, time
- `presentation`: Qt widgets, controllers, signals, view-specific adapters

Rules:

- Business logic does not live in widgets.
- Widgets do not talk directly to Plex or SQLite.
- Infrastructure details do not leak into UI state models.
- Add abstraction only when it removes concrete complexity.

## Repository Shape

```text
src/app/bootstrap/
src/app/domain/
src/app/application/
src/app/infrastructure/
src/app/presentation/
tests/contract/
tests/integration/
tests/smoke/
tests/unit/
scripts/
tools/
docs/
assets/
```

## Product Rules

- Plex PIN login is the primary auth flow.
- `Random Mix` should start fast and keep a short random tail ahead of the current track.
- `Liked Tracks` means Plex `userRating=10`.
- Large sources must load incrementally in both browser and queue-building flows.
- `Play all` on large sources must stream pages into the queue instead of building the full queue synchronously.

## Concurrency Rules

- Qt main thread is only for UI work.
- Network and heavy IO stay off the UI thread.
- Background results return through Qt signals or queued calls.
- Avoid ad hoc threading patterns.
- Avoid rebuilding large widget trees synchronously when appending paged content.

## Persistence Rules

- Use `platformdirs` for config/data/cache/log paths.
- Use JSON for small settings/session files where appropriate.
- Use SQLite for structured caches and playback queue persistence.
- Queue persistence must stay row-based for large playlists.

## Packaging Rules

- `Nuitka` is the primary build path.
- Bundle `libmpv` with packaged apps.
- Bundle reproducible CA data for packaged HTTPS traffic.
- Packaged app naming must stay `Plex Music Player` / `PlexMusicPlayer`.
- Icons used by packaging must come from `assets/`, not archived source trees.

## Testing Rules

- Prefer integration-style behavior tests.
- Cover auth/session lifecycle, queue behavior, paging behavior, playback orchestration, and large-source flows.
- Use contract tests for service/repository boundaries.
- Keep a small smoke surface for Qt startup.

## Performance Rules

- Avoid full-library fetches on browser open.
- Browser lists should page and append instead of clearing and rebuilding from zero when possible.
- Keep artwork caches bounded.
- Waveform rendering must be cached so playback ticks do not repaint full geometry.
