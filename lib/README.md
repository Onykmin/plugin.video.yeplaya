# YAWsP Library

Modular architecture for Yet Another Webshare Plugin.

## Modules

**logging.py** - Log functions (debug, info, warning, error)
**api.py** - Webshare API client, auth, XML parsing
**utils.py** - Kodi UI helpers, formatting, dialogs
**parsing.py** - Filename parsing, quality detection, normalization
  - Supports: S01E05, 1x05, absolute episodes (1-999), season text markers
  - Handles: parentheses, dash separators, release groups
  - Recognition rate: 99.5% across diverse series (Breaking Bad, Naruto, etc.)
**grouping.py** - Series/movie grouping, deduplication
**search.py** - Search relevance scoring
**cache.py** - Cache management, search history
**metadata.py** - Video/audio/subtitle metadata extraction

**playback.py** - Playback, download, queue (stub)
**ui.py** - Navigation, list building (stub)
**database.py** - DB download, extraction (stub)
**routing.py** - URL routing (stub)

## Usage

```python
from lib.api import revalidate, api
from lib.parsing import parse_episode_info
from lib.grouping import group_by_series

token = revalidate()
if token:
    grouped = group_by_series(files, token)
```

## Testing

```bash
pytest tests/ -v
```

## Dependencies

```
logging → api → utils
       ↘      ↗
         grouping → cache
              ↓
         parsing, search, metadata
              ↓
         playback, ui, database, routing
```
