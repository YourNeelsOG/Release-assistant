# Release Assistant v1.0

This project is based on and extends [Audionut's Upload Assistant](https://github.com/Audionut/Upload-Assistant/), with credit to Audionut, wastaken7, and the upstream contributors. Release Assistant combines additional tracker support with local improvements to screenshots, episode handling, and upload safety.

This is a modified version of the Upload Assistant project and is not affiliated with or endorsed by Audionut. It is an unofficial fork, not the official version. The upstream UAPL v1.0 license applies. See [LICENSE](LICENSE).

Generated tool branding is omitted from upload descriptions and torrent metadata. User-configured custom signatures remain available.

## What it does

Prepare movies, television episodes, season packs, and disc releases for private tracker uploads. The assistant inspects media, finds metadata, builds release names and descriptions, takes screenshots, checks duplicates and banned groups, creates torrents, and can add successful uploads to a torrent client.

Features include:

* Tracker-specific naming, categories, release types, descriptions, and upload checks.
* TMDb, IMDb, TVDB, and TVMaze metadata lookups, with manual ID overrides.
* Screenshot capture, image host fallback, image rehosting, and comparison images. Freeimage is available alongside the upstream image hosts.
* Blu-ray and DVD processing, custom descriptions, queues, unattended operation, and manual packaging.
* qBittorrent, rTorrent, Deluge, Transmission, and watch-folder integration, plus cross seeding.
* A local web interface with configuration editing and optional Discord notifications.
* An episode mapping helper that matches service air dates and titles to TVDB numbering.

## Supported trackers

The 68 registered adapters are listed below. Support means an adapter is included. Account permissions, tracker rules, and current site availability still determine whether a particular upload succeeds.

| Code | Tracker | Code | Tracker |
| --- | --- | --- | --- |
| A4K | Aura4K | ACM | AsianCinema |
| AITHER | Aither | ANT | Anthelion |
| AR | Alpharatio | ASC | Amigos-Share |
| AZ | AvistaZ | BHD | Beyond-HD |
| BHDTV | BitHDTV | BJS | BrasilJapão-Share |
| BLU | Blutopia | BT | BrasilTracker |
| CBR | CapybaraBR | CZ | CinemaZ |
| DC | DigitalCore | DP | DeshiPeer |
| DT | DT | EMUW | Emuwarez |
| FF | FunFile | FL | FileList |
| FNP | FearNoPeer | FRIKI | Friki |
| GPW | GreatPosterWall | HDB | HDBits |
| HDS | HD-Space | HDT | HD-Torrents |
| HHD | HomieHelpDesk | HUNO | hawke-uno |
| IHD | InfinityHD | IS | ImmortalSeed |
| ITT | ItaTorrents | LCD | Locadora |
| LDU | LastDigitalUnderground | LST | LST |
| LT | Lat-Team | LUME | Luminarr |
| MTV | MoreThanTV | NBL | Nebulance |
| OE | OnlyEncodes+ | OTW | OldToonsWorld |
| PHD | PrivateHD | PT | Portugas |
| PTER | PTerClub | PTP | PassThePopcorn |
| PTS | PTSKIT | PTT | PolishTorrent |
| R4E | Racing4Everyone | RAS | Rastastugan |
| RF | ReelFLiX | RTF | RetroFlix |
| SAM | Samaritano | SHRI | ShareIsland |
| SN | Swarmazon | SP | seedpool |
| SPD | SpeedApp | STC | SkipTheCommercials |
| THR | TorrentHR | TIK | Cinematik |
| TL | TorrentLeech | TLZ | The Leach Zone |
| TOS | TheOldSchool | TTG | ToTheGlory |
| TTR | Torrenteros | TVC | TVChaosUK |
| ULCX | ULCX | UTP | UTOPIA |
| YOINK | YOiNKED | YUS | YUSCENE |

`DP` means DeshiPeer in this project. It uses a bearer API key and discovers personalized torrent URLs through its authenticated feed. Add your own key to `TRACKERS.DP.api_key`. An account with an accessible feed containing at least one torrent is required for URL discovery.

## Requirements

Use Python 3.11 or newer with pip and virtual environment support. Verification for this distribution used Python 3.14.

Install FFmpeg, ffprobe, MediaInfo, and the MediaInfo shared library using your operating system's package manager. Ensure their executables are on PATH. The assistant can download additional tools for torrent creation and disc inspection when those operations require them. Prebuilt executables are not included in this source distribution. VapourSynth is optional for screenshot workflows that use it.

You need permission to upload at each selected tracker, your own metadata and image host credentials, and a configured torrent client if you want automatic client injection.

## Installation

Open a terminal in this directory. On Linux or macOS:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp data/example-config.py data/config.py
python upload.py --help
```

On Windows, activate the environment with `.venv\Scripts\Activate.ps1` in PowerShell instead. Install the external media tools separately and add them to PATH.

## Configuration

`data/example-config.py` is the published template. `data/config.py` holds your local settings and is ignored by Git. If it is missing, create it:

```sh
cp data/example-config.py data/config.py
```

Edit `data/config.py` as Python code. All API keys, passwords, passkeys, tokens, account identifiers, announce URLs, and client connection settings are empty. Add your own values. Boolean settings and other functional defaults remain populated so the parser can start.

1. Set `DEFAULT.tmdb_api` to your TMDb API key.
2. Choose `DEFAULT.img_host_1` and fill in that host's API key if required. For example, `freeimage` uses `DEFAULT.freeimage_api`. Numbered image host settings provide fallbacks.
3. Complete the labeled section for every tracker you use under `TRACKERS`. Set `TRACKERS.default_trackers` to comma-separated codes, or pass `--trackers` for each run. Cookie-based trackers need your own cookie files under `data/cookies`.
4. If you use TVDB, set `DEFAULT.tvdb_api` and, when your subscription requires it, `DEFAULT.tvdb_pin`. No shared TVDB credential is included. TVDB authentication occurs only when a lookup needs it.
5. For client injection, fill in one `TORRENT_CLIENTS` section and set `DEFAULT.default_torrent_client` to its section name. Configure hosts, ports, credentials, and any path mapping yourself. Automatic client searching starts disabled.
6. Enable optional features such as Discord only after supplying their settings. Update notifications start disabled because this is a separate distribution.

Keep the example template free of credentials. Do not publish your edited configuration, cookies, client session data, or generated working files.

## Usage

Show common options or the full option list:

```sh
python upload.py -h
python upload.py --help
```

Prepare and inspect a movie before uploading:

```sh
python upload.py "media/Movie Name (2025).mkv" --trackers BLU,TL --debug
```

Debug mode suppresses tracker submission. It can still contact metadata services and trackers and upload screenshots to an image host.

Upload a movie with a manual metadata ID:

```sh
python upload.py "media/Movie Name (2025).mkv" --trackers BLU --tmdb movie/12345
```

Prepare a season pack or use a custom description:

```sh
python upload.py "media/Show/Season 01" --trackers BLU,LST --season 1
python upload.py "media/Movie.mkv" --trackers TL --descfile "descriptions/Movie.txt"
```

Complete multi-season packs can use `--season S01-S02` with BLU or LST. Those adapters send the complete-pack season number while retaining the first season for metadata processing. Check other trackers' rules before using a multi-season range.

Process a folder as a named queue:

```sh
python upload.py "media/Incoming" --queue incoming --trackers BLU
```

Start the web interface on its default local address:

```sh
python upload.py --webui
```

Open the local address printed by the program and follow account setup. The command runs the web server instead of starting a command line upload.

Map an episode by its air timestamp and title:

```sh
python tvdb_map.py --tmdb tv/30984 --episode 2026-10-18T15:00:00Z "Episode title"
```

The helper prints JSON with the matching season and episode or an error when the result is missing or ambiguous. It requires your configured TMDb and TVDB access.

## Files

```text
upload.py                  Main command line entry point
tvdb_map.py               Episode mapping helper
discordbot.py             Optional notifications
requirements.txt          Python dependencies
LICENSE                   Upstream license
bin/                      Tool download and disc helper scripts
cogs/                     Output redaction
data/                     Empty configuration, tags, version, and templates
src/                      Preparation, metadata, clients, and tracker adapters
web_ui/                   Web server, authentication, templates, and scripts
```

The program creates working directories and tool downloads as needed. They are not part of the clean source distribution.

## Troubleshooting

* If imports fail, activate the virtual environment and rerun `python -m pip install -r requirements.txt`.
* If configuration parsing fails, check Python syntax, indentation, quotation marks, and commas. Compare the affected section with `data/example-config.py`.
* If metadata lookups fail, verify your own API credentials. TVDB is optional, but features that depend on its episode data need a working key and possibly a subscriber PIN.
* If media inspection or screenshots fail, check that FFmpeg, ffprobe, and MediaInfo work from the same terminal. Disc inspection can require a first-run tool download.
* If tracker authentication fails, check the selected adapter's keys, announce URL, cookie expiry, and upload permissions. DeshiPeer and AvistaZ stop when authentication or upload state cannot be verified.
* If a release is rejected, review the tracker rules and duplicate results before retrying. For DeshiPeer, an accepted upload followed by a failed personalized download requires a manual download rather than another upload.
* If client injection fails, verify client credentials, connection settings, and local-to-remote path mapping.

Live tracker uploads require real accounts and credentials and were not performed during distribution verification.
