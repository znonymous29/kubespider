import unittest
import tempfile
import os
from unittest import mock

from source_provider.ani_source_provider.provider import AniSourceProvider
from utils.config_reader import AbsConfigReader


class AniSourceProviderTest(unittest.TestCase):
    @mock.patch.object(AniSourceProvider, '_load_online_mappings', return_value={})
    def test_season_mapping_legacy(self, _mock_load_online_mappings):
        provider = AniSourceProvider(
            "test",
            MemDictConfigReader({
                'custom_season_mapping': {
                    '千年血戰篇-訣別譚-': 2
                }
            })
        )
        provider.load_config()

        season, keyword, reserve_keywords = provider.get_season('[ANi] BLEACH 死神 千年血戰篇-訣別譚- - 18 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4')

        self.assertEqual(2, season)
        self.assertEqual('千年血戰篇-訣別譚-', keyword)
        self.assertEqual('', reserve_keywords)
        self.assertEqual(
            '[ANi] BLEACH 死神 - S02E18 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4',
            provider.rename_season(
                '[ANi] BLEACH 死神 千年血戰篇-訣別譚- - 18 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4',
                season,
                keyword,
                '18',
                reserve_keywords,
            )
        )

    @mock.patch.object(AniSourceProvider, '_load_online_mappings', return_value={})
    def test_mapping_with_reserve_words(self, _mock_load_online_mappings):
        provider = AniSourceProvider(
            "test",
            MemDictConfigReader({
                'custom_season_mapping': {
                    '千年血戰篇-訣別譚-': {
                        'season': 2,
                        'reserve_keywords': '千年血戰篇'
                    }
                }
            })
        )
        provider.load_config()

        season, keyword, reserve_keywords = provider.get_season('[ANi] BLEACH 死神 千年血戰篇-訣別譚- - 18 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4')

        self.assertEqual(2, season)
        self.assertEqual('千年血戰篇-訣別譚-', keyword)
        self.assertEqual('千年血戰篇', reserve_keywords)
        self.assertEqual(
            '[ANi] BLEACH 死神 千年血戰篇 - S02E18 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4',
            provider.rename_season(
                '[ANi] BLEACH 死神 千年血戰篇-訣別譚- - 18 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4',
                season,
                keyword,
                '18',
                reserve_keywords,
            )
        )

    @mock.patch.object(AniSourceProvider, '_load_online_mappings', return_value={})
    def test_special_episode_skipped(self, _mock_load_online_mappings):
        provider = AniSourceProvider(
            "test",
            MemDictConfigReader({
                'api_type': 'http',
                'classification_on_directory': True,
            })
        )
        provider.load_config()

        anime_info = provider.get_anime_info(
            '[ANi] 杖與劍的魔劍譚 Season 2 - 12.5 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4'
        )
        self.assertIsNotNone(anime_info)
        self.assertEqual('杖與劍的魔劍譚 Season 2', anime_info.title)
        self.assertEqual('12.5', anime_info.episode)
        self.assertTrue(anime_info.is_special_episode)

        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<rss>
  <channel>
    <item>
      <title>[ANi] 杖與劍的魔劍譚 Season 2 - 12.5 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4</title>
      <guid>https://resources.ani.rip/example.mp4</guid>
    </item>
  </channel>
</rss>
'''
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', suffix='.xml', delete=False) as tmp_file:
            tmp_file.write(xml_content)
            tmp_path = tmp_file.name

        try:
            resources = provider.get_links_from_xml(tmp_path, [])
        finally:
            os.unlink(tmp_path)

        self.assertEqual([], resources)

    @mock.patch.object(AniSourceProvider, '_load_online_mappings')
    def test_online_mapping_used_before_builtin_parse(self, mock_load_online_mappings):
        mock_load_online_mappings.return_value = {
            'custom_season_mapping': {
                '杖與劍的魔劍譚 Season 2': {
                    'season': 2,
                    'reserve_keywords': '杖與劍的魔劍譚'
                }
            },
            'season_episode_adjustment': {
                '杖與劍的魔劍譚': {
                    2: -12
                }
            }
        }
        provider = AniSourceProvider(
            "test",
            MemDictConfigReader({})
        )
        provider.load_config()

        season, keyword, reserve_keywords = provider.get_season(
            '[ANi] 杖與劍的魔劍譚 Season 2 - 13 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4'
        )

        self.assertEqual(2, season)
        self.assertEqual('杖與劍的魔劍譚 Season 2', keyword)
        self.assertEqual('杖與劍的魔劍譚', reserve_keywords)
        self.assertEqual(
            '[ANi] 杖與劍的魔劍譚 - S02E01 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4',
            provider.rename_season(
                '[ANi] 杖與劍的魔劍譚 Season 2 - 13 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4',
                season,
                keyword,
                '13',
                reserve_keywords,
            )
        )

    @mock.patch.object(AniSourceProvider, '_load_online_mappings')
    def test_user_mapping_overrides_online_mapping(self, mock_load_online_mappings):
        mock_load_online_mappings.return_value = {
            'custom_season_mapping': {
                '杖與劍的魔劍譚 Season 2': {
                    'season': 2,
                    'reserve_keywords': '杖與劍的魔劍譚'
                }
            },
            'season_episode_adjustment': {
                '杖與劍的魔劍譚': {
                    2: -12
                }
            }
        }
        provider = AniSourceProvider(
            "test",
            MemDictConfigReader({
                'custom_season_mapping': {
                    '杖與劍的魔劍譚 Season 2': {
                        'season': 3,
                        'reserve_keywords': '杖與劍的魔劍譚 自定义'
                    }
                },
                'season_episode_adjustment': {
                    '杖與劍的魔劍譚': {
                        3: -24
                    }
                }
            })
        )
        provider.load_config()

        season, keyword, reserve_keywords = provider.get_season(
            '[ANi] 杖與劍的魔劍譚 Season 2 - 25 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4'
        )

        self.assertEqual(3, season)
        self.assertEqual('杖與劍的魔劍譚 Season 2', keyword)
        self.assertEqual('杖與劍的魔劍譚 自定义', reserve_keywords)
        self.assertEqual(
            '[ANi] 杖與劍的魔劍譚 自定义 - S03E01 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4',
            provider.rename_season(
                '[ANi] 杖與劍的魔劍譚 Season 2 - 25 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4',
                season,
                keyword,
                '25',
                reserve_keywords,
            )
        )

    @mock.patch.object(AniSourceProvider, '_load_online_mappings')
    def test_episode_adjustment_applies_when_mapped_to_season_one(self, mock_load_online_mappings):
        mock_load_online_mappings.return_value = {
            'custom_season_mapping': {
                '出租女友 第五季': {
                    'season': 1,
                    'reserve_keywords': '出租女友'
                }
            },
            'season_episode_adjustment': {
                '出租女友': {
                    1: 48
                }
            }
        }
        provider = AniSourceProvider(
            "test",
            MemDictConfigReader({
                'api_type': 'http',
                'classification_on_directory': True,
            })
        )
        provider.load_config()

        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<rss>
  <channel>
    <item>
      <title>[ANi] 出租女友 第五季 - 01 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4</title>
      <guid>https://resources.ani.rip/example.mp4</guid>
    </item>
  </channel>
</rss>
'''
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', suffix='.xml', delete=False) as tmp_file:
            tmp_file.write(xml_content)
            tmp_path = tmp_file.name

        try:
            resources = provider.get_links_from_xml(tmp_path, [])
        finally:
            os.unlink(tmp_path)

        self.assertEqual(1, len(resources))
        self.assertEqual(
            '[ANi] 出租女友 - S01E49 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4',
            resources[0].extra_params().get('file_name')
        )


class MemDictConfigReader(AbsConfigReader):
    def __init__(self, config: dict) -> None:
        self.config = config

    def save(self, new_data: dict):
        self.config = new_data

    def read(self) -> dict:
        return self.config
