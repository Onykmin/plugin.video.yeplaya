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

**Recommended: Install via Repository (Automatic Updates)**

1. **Download** `repository.yeplaya-1.0.0.zip` from the [GitHub Releases page](https://github.com/Onykmin/plugin.video.yeplaya/releases)
2. Open Kodi and go to **Settings → Add-ons**
3. Click **Install from zip file**
   - **Note:** If this is your first time installing from zip, Kodi will notify you that "Unknown sources" is disabled and redirect you to Settings. Enable it and confirm - this is safe and necessary to install this addon.
4. Select `repository.yeplaya-1.0.0.zip`
5. Wait for "Ye-Playa Repository" installation confirmation
6. Go to **Settings → Add-ons → Install from repository → Ye-Playa Repository → Video add-ons**
7. Select **Ye-Playa** and click Install
8. After installation, right-click on Ye-Playa and select **Settings**
9. Enter your Webshare username and password

**That's it! Future updates will install automatically.**

---

**Alternative: Manual Installation (No Auto-Updates)**

1. Download `plugin.video.yeplaya-X.X.X.zip` from [Releases](https://github.com/Onykmin/plugin.video.yeplaya/releases)
2. Install from zip (same steps as above)
3. You'll need to manually download and install new versions

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
plugin.video.yeplaya/              # Root is the plugin itself
├── addon.xml                      # Plugin metadata and dependencies
├── main.py                        # Entry point, routing, menu generation
├── csfd_scraper.py                # CSFD metadata scraper
├── lib/                           # Modular library (see lib/README.md)
│   ├── api.py                     # Webshare API client
│   ├── parsing.py                 # Filename parsing, quality detection
│   ├── grouping.py                # Series grouping and deduplication
│   ├── cache.py                   # Cache management, search history
│   ├── metadata.py                # Video/audio/subtitle metadata
│   ├── search.py                  # Search relevance scoring
│   ├── utils.py                   # Utilities (normalization, validation)
│   └── logging.py                 # Logging functions
├── tests/                         # Test suite (see tests/README.md)
├── resources/
│   ├── settings.xml               # User configuration UI
│   └── language/
│       └── resource.language.en_gb/
│           └── strings.po         # Localization strings
├── build_zip.sh                   # Build plugin zip (manual)
├── build_zip.py                   # Build plugin zip (Python)
├── repo_generator.py              # Build repository (manual/CI)
├── repository.yeplaya/            # Repository addon
│   ├── addon.xml                  # Points to GitHub for updates
│   ├── icon.png
│   ├── fanart.jpg
│   └── zips/                      # Generated by CI (not in git locally)
│       ├── addons.xml             # Catalog with versions
│       ├── addons.xml.md5         # Checksum
│       ├── plugin.video.yeplaya/
│       │   └── plugin.video.yeplaya-X.X.X.zip
│       └── repository.yeplaya/
│           └── repository.yeplaya-1.0.0.zip
└── .github/workflows/
    └── update-repo.yml            # Auto-build on release tags
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

**For Plugin Only (Manual Testing):**
```bash
./build_zip.sh
# Output: exports/plugin.video.yeplaya-X.X.X.zip
```

**For Repository (Manual Testing):**
```bash
python3 repo_generator.py
# Generates:
# - repository.yeplaya/zips/addons.xml (catalog)
# - repository.yeplaya/zips/plugin.video.yeplaya/plugin.video.yeplaya-X.X.X.zip
# - repository.yeplaya/zips/repository.yeplaya/repository.yeplaya-1.0.0.zip
```

**For Production Release (Automated):**
```bash
# 1. Update version in addon.xml
# 2. Update <news> section in addon.xml
# 3. Commit changes
git add addon.xml
git commit -m "Release vX.X.X: description"

# 4. Merge to main and tag
git checkout main
git merge develop
git tag vX.X.X
git push origin main --tags

# GitHub Action automatically:
# - Runs repo_generator.py
# - Commits zips to main branch
# - Creates GitHub Release
# - Users get auto-update within 24h
```

#### Release Workflow

**Branches:**
- `develop` - Active development
- `main` - Production releases only

**Creating a Release:**

1. **Work on develop branch:**
   ```bash
   git checkout develop
   # Make changes, commit
   ```

2. **Update version:**
   - Edit `addon.xml`: change `version="X.X.X"`
   - Update `<news>` section with changes

3. **Commit and push to develop:**
   ```bash
   git add addon.xml [other files]
   git commit -m "Release vX.X.X: description"
   git push origin develop
   ```

4. **Merge to main and tag:**
   ```bash
   git checkout main
   git merge develop
   git push origin main

   git tag vX.X.X
   git push origin vX.X.X

   git checkout develop
   ```

5. **GitHub Action runs automatically:**
   - Builds plugin and repository zips
   - Commits generated files to main
   - Creates GitHub Release with attachments
   - Users with repository installed get update within 24h

**Testing Locally:**
```bash
# Test plugin build
./build_zip.sh

# Test repository generation
python3 repo_generator.py
```

#### Contributing

1. **Report bugs** via [GitHub Issues](https://github.com/Onykmin/plugin.video.yeplaya/issues)
2. **Submit PRs** to `develop` branch with clear descriptions
3. **Follow existing code style** (4-space indentation, descriptive names)
4. **Test thoroughly** with different Kodi versions and configurations

### License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

See [LICENSE](LICENSE) file for full terms. In summary:
- ✅ Use, modify, and distribute freely
- ✅ Use in commercial projects
- ❗ Must disclose source code of modified versions
