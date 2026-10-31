"""DeshiPeer API uploads using shared preparation and personalized feed downloads."""
import asyncio
import subprocess
import re
from pathlib import Path
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import httpx
from torf import Torrent, TorfError

from src.console import console
from src.get_desc import DescriptionBuilder
from src.trackers.COMMON import COMMON
from src.torrentcreate import TorrentCreator


class DP:
    """Implement the tracker contract with the official bearer-authenticated API."""

    tracker = 'DP'
    source_flag = 'DeshiPeer'
    base_url = 'https://deshipeer.net'
    torrent_url = base_url + '/torrentid='
    banned_groups = []

    def __init__(self, config):
        self.config = config
        self.tracker_config = config['TRACKERS'].setdefault(self.tracker, {})
        self.common = COMMON(config)

    def _client(self, meta):
        """Authenticate API requests without reading cookies or putting keys in URLs."""
        key = str(self.tracker_config.get('api_key') or '').strip()
        if not key:
            raise ValueError('DP API key missing; set TRACKERS.DP.api_key.')
        return httpx.AsyncClient(base_url=self.base_url, headers={'Authorization':'Bearer ' + key},
                                 timeout=30, follow_redirects=False)

    async def _feed(self, client, query=None):
        """Read the authenticated feed, refusing login pages and malformed XML."""
        response = await client.get('/rss', params={'q':query} if query else None)
        response.raise_for_status()
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError:
            raise ValueError('DP API feed is not valid XML; check the API key.') from None
        if root.tag != 'rss' or root.find('channel') is None:
            raise ValueError('DP API feed changed; check the API key and tracker.')
        return root

    def _download_link(self, url):
        """Never forward the bearer key to a host or route supplied by an untrusted feed."""
        target = urljoin(self.base_url, url)
        if not re.fullmatch(re.escape(self.base_url) + r'/dl/[A-Za-z0-9_-]+/\d+\.torrent', target):
            raise ValueError('DP personalized download URL changed or has an unsafe origin.')
        return target

    async def _context(self, client):
        """Discover categories and the account's announce/download URLs through its API feed."""
        if hasattr(self, '_api_context'):
            return self._api_context
        feed = await self._feed(client)
        enclosure = feed.find('./channel/item/enclosure')
        if enclosure is None or not enclosure.get('url'):
            raise ValueError('DP API feed has no personalized torrent to discover the announce URL.')
        download = self._download_link(enclosure.get('url'))
        response = await client.get(download)
        response.raise_for_status()
        personalized = Torrent.read_stream(response.content)
        announce = personalized.metainfo.get('announce', '')
        if not isinstance(announce, str) or not announce.startswith(self.base_url + '/'):
            raise ValueError('DP announce URL changed or is missing.')
        response = await client.get('/torznab/api', params={'t':'caps'})
        response.raise_for_status()
        try:
            caps = ET.fromstring(response.content)
        except ET.ParseError:
            raise ValueError('DP API categories response changed.') from None
        categories = [row.get('name') for row in caps.findall('./categories/category')]
        if not categories:
            raise ValueError('DP API categories are missing.')
        self._download_prefix = download.rsplit('/', 1)[0]
        self._api_context = announce, categories
        return self._api_context

    def _fail(self, meta, message):
        """Store a token-free failure in the status shape expected by the assistant."""
        status = meta.setdefault('tracker_status', {}).setdefault(self.tracker, {})
        status['status_message'] = 'data error: ' + message
        console.print(f'DP: data error: {message}', markup=False, soft_wrap=True)
        return False

    async def validate_credentials(self, meta):
        """Verify API authentication and discover the personalized torrent context."""
        try:
            async with self._client(meta) as client:
                await self._context(client)
            return True
        except (httpx.HTTPError, OSError, ValueError, TorfError):
            meta.setdefault('tracker_status', {}).setdefault('DP', {})['skip_upload'] = True
            return self._fail(meta, 'API authentication or feed discovery failed. Check TRACKERS.DP.api_key and tracker availability.')

    async def get_name(self, meta):
        """Keep the prepared release name unchanged."""
        return {'name': meta['name']}

    async def _dupes(self, client, name):
        """Use API feed search; the upload API also performs authoritative validation."""
        feed = await self._feed(client, name)
        results = []
        for item in feed.findall('./channel/item'):
            title = item.findtext('title')
            enclosure = item.find('enclosure')
            if not title or enclosure is None or not enclosure.get('url'):
                raise ValueError('DP API search entry changed.')
            link = self._download_link(enclosure.get('url'))
            torrent_id = link.rsplit('/', 1)[1].removesuffix('.torrent')
            results.append({'name':title, 'id':torrent_id, 'link':self.torrent_url + torrent_id,
                            'infohash':item.findtext('guid')})
        return results

    async def search_existing(self, meta, _disctype):
        """Return compatible duplicate candidates without a cookie session."""
        async with self._client(meta) as client:
            await self._context(client)
            return await self._dupes(client, meta.get('title') or meta['name'].replace('.', ' '))

    async def edit_desc(self, meta):
        """Reuse the shared BBCode/screenshots and add its existing MediaInfo evidence."""
        builder = DescriptionBuilder(self.tracker, self.config)
        description_meta = dict(meta)
        if meta.get('description_file_content') or meta.get('description_link_content'):
            description_meta['description'] = None
        description = await builder.unit3d_edit_desc(description_meta)
        if meta.get('filelist') and not meta.get('is_disc'):
            media = Path(meta['filelist'][0]).resolve()
            result = await asyncio.to_thread(subprocess.run, ['mediainfo', media.name],
                                             cwd=media.parent, capture_output=True, text=True, check=True)
            mediainfo = result.stdout
        else:
            mediainfo = await builder.get_mediainfo_section(meta)
        bdinfo = await builder.get_bdinfo_section(meta)
        if mediainfo:
            description += '\n[mediainfo]' + mediainfo + '[/mediainfo]\n'
        if bdinfo:
            description += '\n[code]' + bdinfo + '[/code]\n'
        path = Path(meta['base_dir']) / 'tmp' / meta['uuid'] / '[DP]DESCRIPTION.txt'
        path.write_text(description, encoding='utf-8')
        return description

    async def upload(self, meta, _disctype):
        """Submit once, then replace the upload metainfo with the personalized download."""
        status = meta.setdefault('tracker_status', {}).setdefault(self.tracker, {})
        path = Path(meta['base_dir']) / 'tmp' / meta['uuid'] / '[DP].torrent'
        try:
            async with self._client(meta) as client:
                announce, categories = await self._context(client)
                base_path = path.parent / 'BASE.torrent'
                base = Torrent.read(base_path)
                required = 16777216 if base.size > 1073741824 else 1048576
                filename = 'BASE'
                if base.piece_size < required or base_path.stat().st_size > 1048576:
                    if meta.get('nohash'):
                        raise ValueError('DP needs different torrent pieces, but --nohash prevents rebuilding.')
                    # Keep cached torrents intact for other trackers and rebuild only DP's copy.
                    await TorrentCreator.create_torrent(meta, Path(meta['path']), 'DP_BASE')
                    filename = 'DP_BASE'
                await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag,
                                                            torrent_filename=filename, announce_url=announce)
                torrent = Torrent.read(path)
                minimum = 16777216 if torrent.size > 1073741824 else 1048576
                if path.stat().st_size > 1048576 or torrent.piece_size < minimum:
                    raise ValueError('DP requires metainfo <=1 MiB and pieces >=1 MiB, or >=16 MiB above 1 GiB. Recreate the torrent.')
                info = torrent.metainfo['info']
                candidates = await self._dupes(client, meta.get('title') or meta['name'].replace('.', ' '))
                if not meta.get('debug') and any(row.get('infohash') == torrent.infohash for row in candidates):
                    raise ValueError('DP duplicate infohash found. Nothing uploaded.')
                category = 'Anime' if meta.get('anime') else {'MOVIE':'Movies', 'TV':'TV'}.get(meta.get('category'))
                if category not in categories:
                    raise ValueError('DP category is unsupported or its form has changed.')
                imdb = str(meta.get('imdb_id') or '').removeprefix('tt')
                payload = {'name':meta['name'], 'category':category,
                           'imdb':f'https://www.imdb.com/title/tt{imdb.zfill(7)}/' if imdb.isdigit() and int(imdb) else '',
                           'descr':await self.edit_desc(meta)}
                if meta.get('anon') or self.tracker_config.get('anon'):
                    payload['anonymous'] = '1'
                if self.tracker_config.get('seedbox'):
                    payload['seedbox'] = '1'
                if meta.get('debug'):
                    status['status_message'] = 'Debug mode enabled, not uploading'
                    console.print('DP: Debug mode enabled, not uploading')
                    return True
                images = set(re.findall(r'\[img(?:=[^\]]+)?\]\s*(https?://[^\s\[]+)\s*\[/img\]', payload['descr'], re.I))
                if len(images) < 3:
                    raise ValueError('DP requires at least 3 distinct hosted screenshots; nothing uploaded.')
                response = await client.post('/api/upload', data=payload,
                    files={'torrent':(meta['name'] + '.torrent', path.read_bytes(), 'application/x-bittorrent')},
                    headers={'Origin':self.base_url, 'Referer':self.base_url + '/upload'})
                try:
                    data = response.json()
                except ValueError:
                    raise ValueError('DP submission outcome unconfirmed. Check your uploads before retrying.') from None
                if not isinstance(data, dict):
                    raise ValueError('DP submission outcome unconfirmed. Check your uploads before retrying.')
                if not (200 <= response.status_code < 300 and data.get('ok') is True):
                    message = str(data.get('error') or '')
                    quota = re.search(r'exceeded the limit of (\d+) uploads per hour.*?Wait (\d+) minutes',
                                      message, re.I)
                    if quota:
                        limit, minutes = map(int, quota.groups())
                        status.update(rate_limited=True, retry_after=minutes * 60)
                        raise ValueError(f'DP upload limit reached ({limit}/hour). Wait {minutes} minutes; nothing uploaded.')
                    if response.status_code == 429:
                        retry = response.headers.get('Retry-After', '')
                        seconds = int(retry) if retry.isdigit() else 3600
                        status.update(rate_limited=True, retry_after=seconds)
                        raise ValueError('DP API rate limit reached; nothing uploaded. Wait before retrying.')
                    if 400 <= response.status_code < 500 or data.get('ok') is False:
                        raise ValueError(f'DP API rejected the upload (HTTP {response.status_code}); nothing uploaded. Check the tracker rules and release metadata.')
                    raise ValueError('DP submission outcome unconfirmed. Check your uploads before retrying.')
                status['upload_accepted'] = True
                # An accepted upload copy must never reach the client before personalization.
                path.unlink()
                value = data.get('id', data.get('torrent_id'))
                torrent_id = str(value) if str(value).isdigit() and int(value) > 0 else None
                if torrent_id is None:
                    target = urljoin(self.base_url, str(data.get('url') or data.get('torrent_url') or ''))
                    match = re.fullmatch(re.escape(self.torrent_url) + r'(\d+)', target)
                    if match:
                        torrent_id = match.group(1)
                if torrent_id is None:
                    # Feed infohashes provide a verified fallback if the API omits its new ID.
                    feed = await self._feed(client)
                    for item in feed.findall('./channel/item'):
                        enclosure = item.find('enclosure')
                        if item.findtext('guid') == torrent.infohash and enclosure is not None:
                            target = self._download_link(enclosure.get('url', ''))
                            torrent_id = target.rsplit('/', 1)[1].removesuffix('.torrent')
                            break
                if torrent_id is None:
                    raise ValueError('DP accepted the upload but its torrent ID could not be determined.')
                status.update(torrent_id=torrent_id, status_message='Uploaded; retrieving personalized torrent.')
                downloaded = await client.get(self._download_prefix + '/' + torrent_id + '.torrent')
                downloaded.raise_for_status()
                personalized = Torrent.read_stream(downloaded.content)
                if any(personalized.metainfo['info'].get(key) != info.get(key)
                       for key in ('name', 'length', 'files', 'piece length', 'pieces')):
                    raise ValueError('DP personalized torrent does not match the uploaded content.')
                path.write_bytes(downloaded.content)
                status['status_message'] = 'Torrent uploaded successfully; personalized torrent downloaded.'
                return True
        except (httpx.HTTPError, OSError, ValueError, TorfError, subprocess.SubprocessError) as exc:
            if status.get('upload_accepted'):
                location = self.torrent_url + status['torrent_id'] if status.get('torrent_id') else 'DeshiPeer (check My uploads)'
                return self._fail(meta, 'Upload succeeded at ' + location
                                  + ' but its personalized torrent could not be saved. Download it manually; do not re-upload.')
            message = str(exc) if isinstance(exc, ValueError) else 'Request or torrent preparation failed. Check the API key and site before retrying.'
            return self._fail(meta, message)
