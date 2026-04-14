# This works for: https://open.ani.rip
# Function: download anime updated on ANi project
# encoding:utf-8
import logging
import traceback
import xml.etree.ElementTree as ET
import re
from typing import Any, Optional

from source_provider import provider
from api import types
from api.values import Event, Resource
from utils import helper
from utils.config_reader import AbsConfigReader


DEFAULT_SEASON_MAPPER = {
    "第二季": 2,
    "第三季": 3,
    "第四季": 4,
    "第五季": 5,
    "第六季": 6,
    "第七季": 7,
    "第八季": 8,
    "第九季": 9,
    "第十季": 10,
}
ANIME_TITLE_PATTERN = re.compile(
    r'\[ANi\] (.+?) - (\d+(?:\.5)?) \[(.+?)\]\[(.+?)\]\[(.+?)\]\[(.+?)\]\[(.+?)\]\.'
)
SEASON_RENAME_PATTERN = re.compile(r"- (\d+) \[(720P|1080P|4K)\]\[(Baha|Bilibili)\]")
ONLINE_MAPPINGS_URL = 'https://cdn.jsdelivr.net/gh/ChowDPa02k/ani-tmdb-mapper@main/mappings_kubespider.json'


class AnimeReleaseInfo:
    def __init__(self, title: str, episode: str) -> None:
        self.title = title
        self.episode = episode

    @property
    def is_special_episode(self) -> bool:
        return self.episode.endswith('.5')


class SeasonContext:
    def __init__(self, season: int, keyword: Optional[str], reserve_keywords: str) -> None:
        self.season = season
        self.keyword = keyword
        self.reserve_keywords = reserve_keywords


class AniSourceProvider(provider.SourceProvider):
    '''This provider is to sync resources from ANi API: https://api.ani.rip/ani-download.xml
    For the most timely follow-up of Anime updates.
    Downloading media in general HTTP, aria2 provider must be needed.
    '''
    def __init__(self, name: str, config_reader: AbsConfigReader) -> None:
        super().__init__(config_reader)
        self.provider_listen_type = types.SOURCE_PROVIDER_PERIOD_TYPE
        self.webhook_enable = False
        self.provider_type = 'ani_source_provider'
        self.api_type = ''
        self.rss_link = ''
        self.rss_link_torrent = ''
        self.tmp_file_path = '/tmp/'
        self.save_path = 'ANi'
        self.provider_name = name
        self.use_sub_category = False
        self.classification_on_directory = True
        self.blacklist = []
        self.custom_season_mapping = {}
        self.custom_category_mapping = {}
        self.season_episode_adjustment = {}
        self.online_mappings_url = ONLINE_MAPPINGS_URL

    def _get_custom_season_mapping_rule(self, keyword: str) -> tuple[int, str]:
        mapping = self.custom_season_mapping.get(keyword)
        if isinstance(mapping, dict):
            season = mapping.get('season')
            reserve_keywords = mapping.get('reserve_keywords', '')
            if season is None:
                logging.warning('Invalid custom_season_mapping for %s: missing season field', keyword)
                return 1, reserve_keywords
            return season, reserve_keywords
        return mapping, ''

    def _normalize_custom_season_mapping(self, mapping: Any) -> dict[str, Any]:
        if not isinstance(mapping, dict):
            return {}
        normalized = {}
        for keyword, value in mapping.items():
            if isinstance(value, dict):
                season = value.get('season')
                if season is None:
                    logging.warning('Invalid custom_season_mapping for %s: missing season field', keyword)
                    continue
                try:
                    normalized[keyword] = {
                        'season': int(season),
                        'reserve_keywords': str(value.get('reserve_keywords', '')),
                    }
                except (TypeError, ValueError):
                    logging.warning('Invalid custom_season_mapping season for %s: %s', keyword, season)
                continue
            try:
                normalized[keyword] = int(value)
            except (TypeError, ValueError):
                logging.warning('Invalid custom_season_mapping season for %s: %s', keyword, value)
        return normalized

    def _normalize_season_episode_adjustment(self, mapping: Any) -> dict[str, dict[int, int]]:
        if not isinstance(mapping, dict):
            return {}
        normalized = {}
        for title, season_mapping in mapping.items():
            if not isinstance(season_mapping, dict):
                logging.warning('Invalid season_episode_adjustment for %s: %s', title, season_mapping)
                continue
            normalized_title_mapping = {}
            for season, offset in season_mapping.items():
                try:
                    normalized_title_mapping[int(season)] = int(offset)
                except (TypeError, ValueError):
                    logging.warning(
                        'Invalid season_episode_adjustment for %s season %s: %s',
                        title,
                        season,
                        offset
                    )
            if normalized_title_mapping:
                normalized[title] = normalized_title_mapping
        return normalized

    def _load_online_mappings(self) -> dict[str, Any]:
        try:
            req = helper.get_request_controller()
            response = req.get(self.online_mappings_url, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except Exception as err:
            logging.warning('Failed to fetch ani online mappings from %s: %s', self.online_mappings_url, err)
            return {}

        if not isinstance(payload, dict):
            logging.warning('Invalid ani online mappings payload: expected dict, got %s', type(payload).__name__)
            return {}

        return {
            'custom_season_mapping': self._normalize_custom_season_mapping(payload.get('custom_season_mapping', {})),
            'season_episode_adjustment': self._normalize_season_episode_adjustment(
                payload.get('season_episode_adjustment', {})
            ),
        }

    def get_provider_name(self) -> str:
        return self.provider_name

    def get_provider_type(self) -> str:
        return self.provider_type

    def get_provider_listen_type(self) -> str:
        return self.provider_listen_type

    def get_download_provider_type(self) -> str:
        return None

    def get_season(self, title: str) -> tuple[int, Optional[str], str]:
        season_context = self._get_season(title)
        return season_context.season, season_context.keyword, season_context.reserve_keywords

    def _get_season(self, title: str) -> SeasonContext:
        season = 1
        keyword = None
        reserve_keywords = ''
        for kw, value in DEFAULT_SEASON_MAPPER.items():
            if kw in title:
                season = value
                keyword = kw
        for kw in self.custom_season_mapping:
            if kw in title:
                season, reserve_keywords = self._get_custom_season_mapping_rule(kw)
                keyword = kw
        return SeasonContext(season=season, keyword=keyword, reserve_keywords=reserve_keywords)

    def _replace_keyword(self, title: str, season_context: SeasonContext) -> str:
        if not season_context.keyword:
            return title
        replacement = f" {season_context.reserve_keywords}" if season_context.reserve_keywords else ""
        return title.replace(f" {season_context.keyword}", replacement)

    def _get_adjusted_episode(self, title: str, season: int, episode: str) -> str:
        adjusted_episode = int(episode)
        for target_title, season_mapping in self.season_episode_adjustment.items():
            if target_title in title and season in season_mapping:
                adjusted_episode += season_mapping[season]
        return str(adjusted_episode).zfill(2)

    def _has_episode_adjustment(self, title: str, season: int) -> bool:
        for target_title, season_mapping in self.season_episode_adjustment.items():
            if target_title in title and season in season_mapping:
                return True
        return False

    def _rename_season(self, title: str, season_context: SeasonContext, episode: str) -> str:
        season_ = str(season_context.season).zfill(2)
        normalized_title = self._replace_keyword(title, season_context)
        adjusted_episode = self._get_adjusted_episode(title, season_context.season, episode)
        return SEASON_RENAME_PATTERN.sub(
            rf"- S{season_}E{adjusted_episode} [\2][\3]",
            normalized_title
        )

    def rename_season(
        self,
        title: str,
        season: int,
        keyword: Optional[str],
        episode: str,
        reserve_keywords: str = ''
    ) -> str:
        season_context = SeasonContext(season=season, keyword=keyword, reserve_keywords=reserve_keywords)
        return self._rename_season(title, season_context, episode)

    def _get_subcategory(self, title: str, season_context: SeasonContext) -> str:
        # Custom subcategory mapping will cover any generated data
        for mapped_keyword, category in self.custom_category_mapping.items():
            if mapped_keyword in title:
                return category
        # Avoid '/' appear in original Anime title
        # This will be misleading for qbittorrent
        sub_category = title.replace('/', '_')
        if ' - ' in title:
            # Drop English Title
            sub_category = sub_category.split(' - ')[-1]
        if season_context.season > 1 and season_context.keyword:
            # Add Season subcategory
            season_ = str(season_context.season).zfill(2)
            sub_category = sub_category.replace(f" {season_context.keyword}", '') + f"/Season {season_}"
        # According to qbittorrent issue 19941
        # The Windows/linux illegal symbol of path will be automatically replaced with ' '
        # But if the last char of category string is illegal symbol
        # The replaced ' ' end of a path will occur unexpected bug in explorer
        if sub_category[-1] in "<>:\"/\\|?* ":
            sub_category = sub_category[:-1] + "_"
        # Idk why there's one more space ' ' between English Name and Chinese Name
        # The regex just looks fine
        if sub_category[0] == ' ':
            sub_category = sub_category[1:]
        return sub_category

    def _should_skip_release(self, xml_title: str, blacklist: list[str], release_info: Optional[AnimeReleaseInfo]) -> bool:
        if release_info is None:
            return True
        if self.check_blacklist(xml_title, blacklist):
            return True
        if release_info.is_special_episode:
            logging.info('Skip special episode by default: %s', xml_title)
            return True
        return False

    def _normalize_resource_url(self, url: str) -> str:
        if 'resources.ani.rip' not in url:
            return url
        return url.replace('resources.ani.rip', 'cloud.ani-download.workers.dev')

    def _build_resource(
        self,
        xml_title: str,
        anime_info: AnimeReleaseInfo,
        season_context: SeasonContext,
        final_url: str,
    ) -> Resource:
        resource = Resource(
            url=final_url,
            path=self.save_path + (f'/{anime_info.title}' if self.classification_on_directory else ''),
            file_type=types.FILE_TYPE_VIDEO_TV,
            link_type=self.get_link_type(),
        )

        if self.api_type == 'torrent' and self.use_sub_category:
            sub_category = self._get_subcategory(anime_info.title, season_context)
            logging.info('Using subcategory: %s', sub_category)
            resource.put_extra_params({'sub_category': sub_category})

        file_name = xml_title
        if season_context.keyword or self._has_episode_adjustment(xml_title, season_context.season):
            file_name = self._rename_season(xml_title, season_context, anime_info.episode)
        resource.put_extra_params({'file_name': file_name})
        return resource

    def _parse_resource_item(self, item: ET.Element, blacklist: list[str]) -> Optional[Resource]:
        xml_title = item.findtext('./title')
        anime_info = self.get_anime_info(xml_title)
        if self._should_skip_release(xml_title, blacklist, anime_info):
            return None

        season_context = self._get_season(xml_title)
        final_url = self._normalize_resource_url(item.findtext('./guid'))
        resource = self._build_resource(
            xml_title,
            anime_info,
            season_context,
            final_url,
        )
        adjusted_episode = anime_info.episode
        if season_context.keyword or self._has_episode_adjustment(xml_title, season_context.season):
            adjusted_episode = self._get_adjusted_episode(xml_title, season_context.season, anime_info.episode)
        logging.info(
            'Found Anime "%s" Season %s Episode %s -> Adjusted Episode %s, File "%s"',
            anime_info.title,
            season_context.season,
            anime_info.episode,
            adjusted_episode,
            resource.extra_param('file_name')
        )
        return resource

    def get_prefer_download_provider(self) -> list:
        downloader_names = self.config_reader.read().get('downloader', None)
        if downloader_names is None:
            return None
        if isinstance(downloader_names, list):
            return downloader_names
        return [downloader_names]

    def get_download_param(self) -> dict:
        return self.config_reader.read().get('download_param', {})

    def get_link_type(self) -> str:
        return types.LINK_TYPE_TORRENT if self.api_type == 'torrent' else types.LINK_TYPE_GENERAL

    def provider_enabled(self) -> bool:
        return self.config_reader.read().get('enable', True)

    def is_webhook_enable(self) -> bool:
        return self.webhook_enable

    def should_handle(self, event: Event) -> bool:
        return False

    def get_links(self, event: Event) -> list[Resource]:
        try:
            req = helper.get_request_controller()
            api = self.rss_link_torrent if self.api_type == 'torrent' else self.rss_link
            links_data = req.get(api, timeout=30).content
        except Exception as err:
            logging.info('Error while fetching ANi API: %s', err)
            return []
        tmp_xml = helper.get_tmp_file_name('') + '.xml'
        with open(tmp_xml, 'wb') as cfg_file:
            cfg_file.write(links_data)
            cfg_file.close()
        blacklist = self.load_filter_config()
        return self.get_links_from_xml(tmp_xml, blacklist)

    def get_links_from_xml(self, tmp_xml, blacklist) -> list[Resource]:
        try:
            resources = []
            for item in ET.parse(tmp_xml).findall('.//item'):
                resource = self._parse_resource_item(item, blacklist)
                if resource is not None:
                    resources.append(resource)
            return resources
        except Exception as err:
            print(traceback.format_exc())
            logging.info('Error while parsing RSS XML: %s', err)
            return []

    def get_anime_info(self, title: str) -> Optional[AnimeReleaseInfo]:
        '''Extract info by only REGEX, might be wrong in extreme cases.
        '''
        matches = ANIME_TITLE_PATTERN.match(title)
        if matches is None:
            logging.warning('Error while running regex on title %s', title)
            return None
        anime_title = matches.group(1)
        episode = matches.group(2)
        return AnimeReleaseInfo(title=anime_title, episode=episode)

    def load_filter_config(self) -> str:
        filter_ = self.config_reader.read().get('blacklist', None)

        if filter_ is None or filter_ == "":
            return []
        if isinstance(filter_, list):
            return [str(item) for item in filter_]
        if isinstance(filter_, str):
            return [filter_]
        logging.warning('Invalid blacklist value: %s, fallback to Empty', filter_)
        return []

    def check_blacklist(self, text: str, blacklist: list) -> bool:
        for item in blacklist:
            if item in text:
                logging.info('File %s will be ignored due to blacklist matched: %s', text, item)
                return True
        return False

    def update_config(self, event: Event) -> None:
        pass

    def load_config(self) -> None:
        cfg = self.config_reader.read()
        logging.info('Ani will use %s API', cfg.get('api_type'))
        self.api_type = cfg.get('api_type')
        self.rss_link = cfg.get('rss_link')
        self.rss_link_torrent = cfg.get('rss_link_torrent')
        self.use_sub_category = cfg.get('use_sub_category', False)
        self.classification_on_directory = cfg.get('classification_on_directory', True)
        online_mappings = self._load_online_mappings()
        online_custom_season_mapping = online_mappings.get('custom_season_mapping', {})
        online_season_episode_adjustment = online_mappings.get('season_episode_adjustment', {})
        user_custom_season_mapping = self._normalize_custom_season_mapping(cfg.get('custom_season_mapping', {}))
        user_season_episode_adjustment = self._normalize_season_episode_adjustment(
            cfg.get('season_episode_adjustment', {})
        )
        self.custom_season_mapping = {
            **online_custom_season_mapping,
            **user_custom_season_mapping,
        }
        self.custom_category_mapping = cfg.get('custom_category_mapping', {})
        self.season_episode_adjustment = {
            **online_season_episode_adjustment,
            **user_season_episode_adjustment,
        }
