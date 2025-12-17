# Ye-Playa

**Search and stream videos from Webshare.cz directly in Kodi**

> Based on [YAWsP](https://www.xbmc-kodi.cz/prispevek-yet-another-webshare-plugin) by cache-sk

---

## For Users

### What is this?

Ye-Playa lets you search and watch videos from **Webshare.cz** (a file-sharing service like Google Drive or Dropbox) directly in your Kodi media center.

This addon is primarily used in the **Czech Republic and Slovakia**, where Webshare is popular. Most content is in Czech/Slovak language.

### What You Need

- **A Webshare.cz account** – Sign up at [webshare.cz](https://webshare.cz)
- **Kodi 19 or newer** – Works on all platforms (Windows, Linux, Mac, Android, etc.)

That's it!

### How to Install

1. **Download** the latest `.zip` file from the [GitHub Releases page](https://github.com/Onykmin/plugin.video.yeplaya/releases)
2. Open Kodi and go to **Settings → Add-ons**
3. Click **Install from zip file**
   - **Note:** If this is your first time installing from zip, Kodi will notify you that "Unknown sources" is disabled and redirect you to Settings. Enable it and confirm - this is safe and necessary to install this addon.
4. Select the downloaded `.zip` file
5. Wait for the installation confirmation
6. Find the addon in Kodi: **Videos → Video add-ons → Ye-Playa**
7. Right-click (or long-press) on Ye-Playa and select **Settings**
8. Enter your Webshare username and password

### What You Can Do

#### Finding Content
- **Search** for movies and TV shows by name
- **Browse** recent or popular files on Webshare
- **Quick access** to your previous searches

#### Watching
- **Stream videos** directly in Kodi (no download needed)
- **Choose quality** when multiple versions available (HD, 4K, etc.)
- Search works **with or without accents** (e.g., "cesky" finds "český")

#### Organizing
- **TV shows grouped** by season and episode automatically
- **Watch history** keeps track of what you've seen
- **Smart grouping** eliminates duplicate listings

#### Downloading
- **Save videos** to your computer for offline viewing
- **Download queue** for multiple files at once
- Files saved with proper names automatically

---

## For Developers

### Technical Overview

Ye-Playa is a Kodi video plugin that integrates with the Webshare.cz API to provide search, streaming, and download functionality.

**Key Features:**
- Smart series grouping and deduplication with hierarchical navigation
- Advanced episode parsing supporting multiple formats:
  - Standard: S01E05, 1x05
  - Absolute episodes: "Series - 377", "Series 125"
  - Season text: "2nd Season", "Season 2"
  - Parentheses: "(S01E01)", "[S02E05]"
  - Release groups: Automatically stripped from "[Group] Series - 01"
- Quality ranking algorithm (resolution + source + codec scoring)
- Unicode normalization for Czech/Slovak character searching
- Session-based authentication with MD5 digest
- Download queue management with progress notifications

**Stack:**
- Python 3 (Kodi Python API 3.0.0+)
- Kodi Matrix (19.x) or newer
- License: AGPL 3.0

### Requirements

**Runtime:**
- Kodi version: 19.x (Matrix) or newer
- Python: 3.0+ (provided by Kodi)

**Dependencies:**
- `script.module.requests` (2.18.4+) – HTTP client
- `script.module.unidecode` (0.4.16+) – Unicode normalization (with fallback)

**External:**
- Webshare.cz account with valid credentials
- Internet connection for API access

### Project Structure

```
plugin.video.yeplaya/
├── addon.xml              # Addon metadata and dependencies
├── main.py                # Entry point, routing, and menu generation
├── lib/                   # Modular library (see lib/README.md)
│   ├── api.py             # Webshare API client (auth, search, streaming)
│   ├── parsing.py         # Filename parsing, quality detection
│   ├── grouping.py        # Series grouping and deduplication logic
│   ├── cache.py           # Cache management, search history
│   ├── metadata.py        # Video/audio/subtitle metadata extraction
│   ├── search.py          # Search relevance scoring
│   ├── utils.py           # Utilities (normalization, validation)
│   └── logging.py         # Logging functions
├── tests/                 # Test suite (see tests/README.md)
├── resources/
│   ├── settings.xml       # User configuration UI definitions
│   └── language/
│       └── resource.language.en_gb/
│           └── strings.po # Localization strings
└── README.md
```

**Documentation:**
- [lib/README.md](lib/README.md) – Library modules, usage, dependencies
- [tests/README.md](tests/README.md) – Test suite overview, runners

### Configuration

The addon's behavior is controlled via `resources/settings.xml`:

**Account Settings:**
- `username` – Webshare.cz username
- `password` – Webshare.cz password (hidden input)
- `token` – Session token (auto-managed)

**Search Preferences:**
- `category` – Default search category filter (Video, Audio, etc.)
- `sort` – Default sort order (Relevance, Recent, Largest, etc.)
- `limit` – Results per page (default: 25)
- `searches` – Number of searches to remember (default: 20)

**Display Options:**
- `show_size` – Show file size in listings (bool)
- `label` – Custom label format with `{name}` and `{size}` placeholders
- `default_view` – Series view (grouped) or flat file list

**Download Settings:**
- `download_folder` – Local folder path for downloads
- `normalize_filenames` – Remove special characters on download (bool)
- `download_notifications` – Show progress notifications (bool)

**Advanced:**
- `experimental` – Enable experimental features (bool)
- `group_movies` – Group movies by title and year (bool)
- `csfd_integration` – Enable CSFD metadata lookup (bool, currently disabled)

### Development

#### Setup for Development

1. Clone the repository:
   ```bash
   git clone https://github.com/Onykmin/plugin.video.yeplaya.git
   cd plugin.video.yeplaya
   ```

2. Symlink to your Kodi addons directory:
   ```bash
   # Linux/Mac
   ln -s $(pwd) ~/.kodi/addons/plugin.video.yeplaya

   # Windows (as Administrator)
   mklink /D "%APPDATA%\Kodi\addons\plugin.video.yeplaya" "C:\path\to\repo"
   ```

3. Enable addon in Kodi and configure credentials
   - **Note:** Kodi will automatically install dependencies (`script.module.requests`, `script.module.unidecode`) from addon.xml when you enable the addon

#### Testing Changes

- **Restart Kodi** after code changes (or disable/enable addon)
- Check `kodi.log` for errors and debug output:
  ```bash
  # Linux
  tail -f ~/.kodi/temp/kodi.log | grep Ye-Playa

  # Windows
  # See: %APPDATA%\Kodi\kodi.log
  ```

#### Building Distribution

Use the build scripts to create installable ZIP:

```bash
# Bash
./build_zip.sh

# Or Python
./build_zip.py
```

Output: `exports/plugin.video.yeplaya-<version>.zip`

Both scripts:
- Clean old builds
- Create distribution package
- Exclude dev files (.git, tests, __pycache__)
- Show SHA256 checksum

#### Contributing

1. **Report bugs** via [GitHub Issues](https://github.com/Onykmin/plugin.video.yeplaya/issues)
2. **Submit PRs** with clear descriptions of changes
3. **Follow existing code style** (4-space indentation, descriptive names)
4. **Test thoroughly** with different Kodi versions and configurations

### License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

See [LICENSE](LICENSE) file for full terms. In summary:
- ✅ Use, modify, and distribute freely
- ✅ Use in commercial projects
- ❗ Must disclose source code of modified versions
