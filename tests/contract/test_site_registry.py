import unittest
import base64
import json

from wuxing.config.site_loader import load_site_configs
from wuxing.domain.enums import FetchStrategy, SourceKind
from wuxing.domain.models import SourceDocument
from wuxing.registry import build_site_registry
from wuxing import registry_data
from wuxing.validation.result import validate_scrape_candidates


class SiteRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sites = load_site_configs("sites.json", allow_legacy=True)
        cls.registry = build_site_registry(cls.sites)

    def test_every_formal_site_has_one_unique_rule(self):
        self.assertEqual(len(self.registry), 153)
        rules = [self.registry.require(site.site_id) for site in self.sites]
        self.assertEqual(len({rule.site_id for rule in rules}), 153)
        self.assertEqual(len({rule.rule_id for rule in rules}), 153)
        self.assertEqual(len({rule.parser_id for rule in rules}), 153)
        self.assertTrue(all(rule.parser is not None for rule in rules))

    def test_special_parser_is_bound_by_parser_id(self):
        site = next(site for site in self.sites if site.name == "八级心动")
        rule = self.registry.require(site.site_id)
        self.assertEqual(rule.parser_id, "parser.bajixindong.v2")

    def test_shared_url_sites_keep_separate_rules(self):
        shared = [site for site in self.sites if site.shared_source_id]
        rules = [self.registry.require(site.site_id) for site in shared]

        self.assertEqual(len(shared), 2)
        self.assertEqual(len({rule.rule_id for rule in rules}), 2)

    def test_fetch_strategy_is_explicit_for_dynamic_and_spa_sites(self):
        article = next(site for site in self.sites if site.api_url)
        spa = next(site for site in self.sites if "#/users/" in site.url)

        self.assertIs(self.registry.require(article.site_id).fetch_strategy, FetchStrategy.ARTICLE_API)
        self.assertIs(self.registry.require(spa.site_id).fetch_strategy, FetchStrategy.SPA_API)

    def test_215_rendered_only_repairs_use_browser_first_and_keep_direction_windows(self):
        cases = {
            "无懈可击": ("top", "金行", "215期【稳杀一行】【金】开0000准\n214期【稳杀一行】【土】开兔04准\n213期【稳杀一行】【水】开猴35准\n212期【稳杀一行】【火】开牛06准"),
            "心如刀割": ("top", "火行", "215期:绝杀(1)行【火行】开:000准\n214期:绝杀(1)行【火行】开:兔04准\n213期:绝杀(1)行【木行】开:猴35准\n212期:绝杀(1)行【水行】开:牛06准"),
            "雕虫小事": ("top", "火行", "215期：▼绝杀一行▼【火】开00对\n214期：▼绝杀一行▼【水】开兔04对\n213期：▼绝杀一行▼【土】开猴35对\n212期：▼绝杀一行▼【金】开牛06对"),
            "王六杀一行": ("top", "木行", "215期:王 六☆杀一行【木行】开:0000赢\n214期:王 六☆杀一行【火行】开:兔04赢\n213期:王 六☆杀一行【金行】开:猴35错\n212期:王 六☆杀一行【水行】开:牛06赢"),
            "精枝玉叶": ("bottom", "土行", "212期:绝杀(1)行【火行】开牛06赢\n213期:绝杀(1)行【金行】开猴35错\n214期:绝杀(1)行【水行】开兔04赢\n215期:绝杀(1)行【土行】开0000赢"),
            "头昏眼花": ("top", "金行", "215期:绝杀1行【金行】开:000准\n214期:绝杀1行【火行】开:兔04准\n213期:绝杀1行【火行】开:猴35准\n212期:绝杀1行【土行】开:牛06准"),
            "违害就利": ("top", "土行", "215期：▼绝杀一行▼【土】开0000对\n214期：▼绝杀一行▼【水】开兔04对\n213期：▼绝杀一行▼【金】开猴35错\n212期：▼绝杀一行▼【火】开牛06对"),
            "光阴似箭": ("top", "木行", "215期【绝杀一行】【木】开0000准\n214期【绝杀一行】【土】开兔04准\n213期【绝杀一行】【金】开猴35错\n212期【绝杀一行】【水】开牛06准"),
            "恭喜发财": ("top", "火行", "215期☆绝杀一行☆【火】开000准\n214期☆绝杀一行☆【土】开兔04准\n213期☆绝杀一行☆【金】开猴35错\n212期☆绝杀一行☆【水】开牛06准"),
            "斤斤计较": ("top", "金行", "215期【绝杀一行】【杀金行】开:000对\n214期【绝杀一行】【杀火行】开:兔04对\n213期【绝杀一行】【杀木行】开:猴35对\n212期【绝杀一行】【杀水行】开:牛06对"),
            "六玄": ("top", "金行", "215期 绝杀一行【金 行】开0000准\n214期 绝杀一行【土 行】开兔04准\n213期 绝杀一行【水 行】开猴35准\n212期 绝杀一行【火 行】开牛06准"),
            "神机": ("top", "金行", "绝杀一行）215期稳杀(1)行【金金金】开0000√"),
            "十全十美": ("bottom", "金行", "212期:绝杀(1)行【火行】开:牛06准\n213期:绝杀(1)行【土行】开:猴35准\n214期:绝杀(1)行【金行】开:兔04错\n215期:绝杀(1)行【金行】开:？00准"),
        }

        for name, (region, expected_wuxing, rendered_text) in cases.items():
            with self.subTest(name=name):
                site = next(site for site in self.sites if site.name == name)
                rule = self.registry.require(site.site_id)
                document = SourceDocument(
                    f"{site.site_id}-rendered-215",
                    site.url,
                    SourceKind.BROWSER,
                    rendered_text,
                    0,
                    metadata=(("capture_part", "body"),),
                    rendered=True,
                )

                self.assertEqual(site.region.value, region)
                self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
                authoritative = rule.select_authority((document,), 215)
                candidates = rule.parse(authoritative)
                target = validate_scrape_candidates(site, 215, candidates, authoritative)
                missing = validate_scrape_candidates(site, 216, candidates, authoritative)

                self.assertTrue(target.passed)
                self.assertEqual(target.candidate.wuxing, expected_wuxing)
                self.assertFalse(missing.passed)
                self.assertEqual(missing.failure_code.value, "TARGET_NOT_FOUND")

    def test_taolibuyan_uses_browser_first_with_its_rendered_anchor(self):
        site = next(site for site in self.sites if site.name == "桃李不言")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertRegex(
            "特料帖213期:【绝杀一行】 作者:桃李不言",
            rule.browser_plan.required_text_pattern,
        )

    def test_taolibuyan_rendered_rows_validate_inside_top_window(self):
        site = next(site for site in self.sites if site.name == "桃李不言")
        rule = self.registry.require(site.site_id)
        document = SourceDocument(
            "taolibuyan-rendered",
            site.url,
            SourceKind.BROWSER,
            "特料帖213期:【绝杀一行】 作者:桃李不言\n"
            "213期【绝杀一行】【杀木行】开0000对\n"
            "212期【绝杀一行】【杀金行】开牛06对\n"
            "211期【绝杀一行】【杀水行】开马01错\n"
            "210期【绝杀一行】【杀火行】开马49错",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )

        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "木行")

    def test_tongxin_yeli_uses_browser_first_with_bottom_block(self):
        site = next(site for site in self.sites if site.name == "同心叶力")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "绝杀料213期:【绝杀一行】 作者:同心叶力",
            rule.browser_plan.required_text_pattern,
        )

        document = SourceDocument(
            "tongxin-yeli-rendered",
            site.url,
            SourceKind.BROWSER,
            "绝杀料213期:【绝杀一行】 作者:同心叶力\n"
            "365期【绝杀一行】【杀水行】开:龙26对\n"
            "001期【绝杀一行】【杀火行】开:牛29对\n"
            "211期【绝杀一行】【杀木行】开:马01对\n"
            "212期【绝杀一行】【杀金行】开:牛06对\n"
            "213期【绝杀一行】【杀土行】开:？00对\n"
            "澳门开奖站\n"
            "214期【绝杀一行】【杀火行】开:狗44对",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "土行")

    def test_aomen_chuangfu_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "澳门创富网")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "澳门创富 『绝杀一行』 213期",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "aomen-chuangfu-rendered",
            site.url,
            SourceKind.BROWSER,
            "澳门创富 『绝杀一行』\n"
            "213期【绝杀一行】【水行】开0000准\n"
            "212期【绝杀一行】【火行】开牛06准\n"
            "211期【绝杀一行】【木行】开马01准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "水行")

    def test_pingtewangxin_uses_visible_browser_block_for_bottom_window(self):
        site = next(site for site in self.sites if site.name == "平特网心")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "213期:平特网心水【绝杀一行】",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "pingtewangxin-rendered",
            site.url,
            SourceKind.BROWSER,
            "213期:绝杀(1)行【木行】开猴35准\n"
            "212期:绝杀(1)行【火行】开牛06错\n"
            "211期:绝杀(1)行【金行】开马01准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "木行")

    def test_aomen_jindiaotong_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "澳门精吊桶")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "澳门金吊桶 ▼绝杀一行▼ 213期",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "aomen-jindiaotong-rendered",
            site.url,
            SourceKind.BROWSER,
            "澳门金吊桶 ▼绝杀一行▼\n"
            "213期【绝杀一行】【水行】开猴35准\n"
            "212期【绝杀一行】【火行】开金06错\n"
            "211期【绝杀一行】【木行】开马01准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "水行")

    def test_zhishenshwai_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "置身事外")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "213期:澳门马票【绝杀一行】免费公開 作者:置身事外",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "zhishenshwai-rendered",
            site.url,
            SourceKind.BROWSER,
            "213期:澳门马票【绝杀一行】免费公開 作者:置身事外\n"
            "213期【绝杀一行】【杀木行】开000对\n"
            "212期【绝杀一行】【杀土行】开牛06错\n"
            "211期【绝杀一行】【杀火行】开马01对",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "木行")

    def test_dimeizheyao_uses_visible_browser_block_for_bottom_window(self):
        site = next(site for site in self.sites if site.name == "低眉折腰")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "精华资料214期:【绝杀一行】重磅来袭 作者:低眉折腰",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "dimeizheyao-rendered",
            site.url,
            SourceKind.BROWSER,
            "精华资料214期:【绝杀一行】重磅来袭 作者:低眉折腰\n"
            "214期【绝杀一行】【火行】开0000对\n"
            "213期【绝杀一行】【水行】开猴35对\n"
            "212期【绝杀一行】【金行】开牛06对",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "水行")

    def test_linglingsansan_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "零零散散")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "零零散散 发表于 213期:绝杀(1)行",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "linglingsansan-rendered",
            site.url,
            SourceKind.BROWSER,
            "零零散散 发表于 213期:绝杀(1)行\n"
            "213期:绝杀(1)行【土行】开:？00赢\n"
            "212期:绝杀(1)行【火行】开:牛06赢\n"
            "211期:绝杀(1)行【木行】开:马01赢",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "土行")

    def test_chanshengongming_uses_visible_browser_block_for_bottom_window(self):
        site = next(site for site in self.sites if site.name == "产生共鸣")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "产生共鸣 稳杀一行 213期稳杀一行【水】",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "chanshengongming-rendered",
            site.url,
            SourceKind.BROWSER,
            "产生共鸣 稳杀一行\n"
            "211期稳杀一行【金】开马01准\n"
            "212期稳杀一行【土】开牛06错\n"
            "213期稳杀一行【水】开猴35准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "水行")

    def test_zhuangyuanhong_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "狀元紅")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "狀元紅⊙『绝杀①行』 213期",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "zhuangyuanhong-rendered",
            site.url,
            SourceKind.BROWSER,
            "狀元紅⊙『绝杀①行』\n"
            "214期:绝杀①行【火行】开0000准\n"
            "213期:绝杀①行【木行】开猴35准\n"
            "212期:绝杀①行【土行】开牛06准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "木行")

    def test_haofangbuji_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "豪放不羁")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "214期：豪放不羁《绝杀一行》已更新 作者:豪放不羁",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "haofangbuji-rendered",
            site.url,
            SourceKind.BROWSER,
            "214期：豪放不羁《绝杀一行》已更新 作者:豪放不羁\n"
            "214期：绝杀一行【水水水】开：0000准\n"
            "213期：绝杀一行【木木木】开：猴35准\n"
            "212期：绝杀一行【火火火】开：牛06准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "木行")

    def test_jinfeixibi_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "今非昔比")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "213期：今非昔比《绝杀一行》准准准 作者:今非昔比",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "jinfeixibi-rendered",
            site.url,
            SourceKind.BROWSER,
            "213期：今非昔比《绝杀一行》准准准 作者:今非昔比\n"
            "213期:绝杀①行【火行】开0000赢\n"
            "212期:绝杀①行【水行】开牛06赢\n"
            "211期:绝杀①行【木行】开马01赢",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "火行")

    def test_qianyanyanyu_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "千言万语")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "网红帖213期:【绝杀一行】 作者:千言万语",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "qianyanyanyu-rendered",
            site.url,
            SourceKind.BROWSER,
            "网红帖213期:【绝杀一行】 作者:千言万语\n"
            "213期：▼绝杀一行▼【水】开0000对\n"
            "212期：▼绝杀一行▼【木】开牛06对\n"
            "211期：▼绝杀一行▼【水】开马01错",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "水行")

    def test_sunrenliji_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "损人利己")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "特码料214期:【绝杀一行】损人利己 损人利己发表于",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "sunrenliji-rendered",
            site.url,
            SourceKind.BROWSER,
            "特码料214期:【绝杀一行】损人利己 损人利己发表于\n"
            "214期【绝杀一行】【杀木行】开0000对\n"
            "213期【绝杀一行】【杀水行】开猴35对\n"
            "212期【绝杀一行】【杀土行】开牛06错",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "水行")

    def test_yihubaiying_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "一呼百应")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "精华帖子214期:〓【稳杀一行】〓期期准确 一呼百应",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "yihubaiying-rendered",
            site.url,
            SourceKind.BROWSER,
            "精华帖子214期:〓【稳杀一行】〓期期准确 一呼百应\n"
            "214期:〓【稳杀一行】〓【水行】开：00赢\n"
            "213期:〓【稳杀一行】〓【水行】开：猴35赢\n"
            "212期:〓【稳杀一行】〓【木行】开：牛06赢",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "水行")

    def test_zhugouburu_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "猪狗不如")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "213期【绝杀一行】已公开 猪狗不如 发表于",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "zhugouburu-rendered",
            site.url,
            SourceKind.BROWSER,
            "213期【绝杀一行】已公开 猪狗不如 发表于\n"
            "213期:〓【绝杀一行】〓【水行】开:0000赢\n"
            "212期:〓【绝杀一行】〓【火行】开:牛06赢\n"
            "211期:〓【绝杀一行】〓【火行】开:马01赢",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "水行")

    def test_jianglongyouhui_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "降龙有悔")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "214期【绝杀一行】 降龙有悔 发表于",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "jianglongyouhui-rendered",
            site.url,
            SourceKind.BROWSER,
            "214期【绝杀一行】 降龙有悔 发表于\n"
            "214期:绝杀(1)行【土行】开0000赢\n"
            "213期:绝杀(1)行【水行】开猴35赢\n"
            "212期:绝杀(1)行【火行】开牛06赢",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "水行")

    def test_manhquanxi_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "满汉全席")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "满汉全席发文 214期绝杀一行",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "manhquanxi-rendered",
            site.url,
            SourceKind.BROWSER,
            "满汉全席发文\n"
            "214期:绝杀一行【火行】開:0000准\n"
            "213期:绝杀一行【木行】開:猴35准\n"
            "212期:绝杀一行【水行】開:牛06准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "木行")

    def test_xinfengluntan_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "信封论坛")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "澳门信封论坛 绝杀一行 213期",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "xinfengluntan-rendered",
            site.url,
            SourceKind.BROWSER,
            "澳门信封论坛 绝杀一行\n"
            "213期：[绝杀一行] [水行]\n"
            "212期：[绝杀一行] [火行]\n"
            "211期：[绝杀一行] [木行]",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "水行")

    def test_baiwanziliao_clicks_explicit_tab_and_uses_visible_block(self):
        site = next(site for site in self.sites if site.name == "百万资料")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertEqual(rule.browser_plan.tab_label_pattern, r"^杀一行$")
        self.assertEqual(rule.browser_plan.popup_close_selector, "#pop-xyz .pop-xyz-close")
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertFalse(rule.browser_plan.ocr_script)
        self.assertRegex(
            "百万资料库\n杀一行\n215期稳杀(1)行",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "baiwanziliao-rendered",
            site.url,
            SourceKind.BROWSER,
            "百万资料库\n杀一行\n"
            "215期稳杀(1)行【土】开0000准\n"
            "214期稳杀(1)行【金】开兔04错\n"
            "213期稳杀(1)行【火】开猴35准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 215)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 215, candidates, authoritative)
        missing = validate_scrape_candidates(site, 216, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "土行")
        self.assertFalse(missing.passed)
        self.assertEqual(missing.failure_code.value, "TARGET_NOT_FOUND")

    def test_bajixindong_and_babumaoge_disable_wrong_click_and_ocr_fallbacks(self):
        cases = {
            "八级心动": (
                "八级心动【绝杀一行】\n"
                "215期绝杀一行【土行】开？00准\n"
                "214期绝杀一行【火行】开兔04准\n"
                "212期绝杀一行【水行】开牛06准",
                "土行",
            ),
            "八步毛哥": (
                "八步毛哥【必杀一行】\n"
                "216期：必杀一行【水行】开？00中\n"
                "215期：必杀一行【金行】开蛇14中\n"
                "214期：必杀一行【土行】开兔04中",
                "金行",
            ),
        }
        for name, (rendered_text, expected_wuxing) in cases.items():
            with self.subTest(name=name):
                site = next(site for site in self.sites if site.name == name)
                rule = self.registry.require(site.site_id)
                self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
                self.assertEqual(rule.browser_plan.exact_click_path, "")
                self.assertFalse(rule.browser_plan.ocr_script)
                document = SourceDocument(
                    f"{site.site_id}-rendered-215",
                    site.url,
                    SourceKind.BROWSER,
                    rendered_text,
                    0,
                    metadata=(("capture_part", "body"),),
                    rendered=True,
                )
                authoritative = rule.select_authority((document,), 215)
                candidates = rule.parse(authoritative)
                decision = validate_scrape_candidates(site, 215, candidates, authoritative)
                missing = validate_scrape_candidates(site, 217, candidates, authoritative)

                self.assertTrue(decision.passed)
                self.assertEqual(decision.candidate.wuxing, expected_wuxing)
                self.assertFalse(missing.passed)
                self.assertEqual(missing.failure_code.value, "TARGET_NOT_FOUND")

    def test_erlizhinian_allows_nonblocking_browser_load(self):
        site = next(site for site in self.sites if site.name == "而立之年")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertIn(site.url, registry_data.BROWSER_NON_BLOCKING_LOAD_URLS)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "精华料213期:【必杀一行】 而立之年 发表于",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "erlizhinian-rendered",
            site.url,
            SourceKind.BROWSER,
            "精华料213期:【必杀一行】 而立之年 发表于\n"
            "213期：必杀一行【水行】特0000准\n"
            "212期：必杀一行【火行】特牛06准\n"
            "211期：必杀一行【土行】特马01准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "水行")

    def test_cangbaoge_uses_browser_page_source_for_top_window(self):
        site = next(site for site in self.sites if site.name == "藏宝阁")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertFalse(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "藏宝图稳杀一行 213期",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "cangbaoge-rendered",
            site.url,
            SourceKind.BROWSER,
            "藏宝图稳杀一行\n"
            "213期稳杀一行【金行】\n"
            "212期稳杀一行【火行】\n"
            "211期稳杀一行【水行】",
            0,
            metadata=(("capture_part", "page_source"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "金行")

    def test_suanfawenxin_uses_visible_browser_block_for_bottom_window(self):
        site = next(site for site in self.sites if site.name == "算法文心")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "算法文心 213期:绝杀(1)行",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "suanfawenxin-rendered",
            site.url,
            SourceKind.BROWSER,
            "算法文心 213期:绝杀(1)行\n"
            "211期:绝杀(1)行【金行】开马01准\n"
            "212期:绝杀(1)行【水行】开牛06赢\n"
            "213期:绝杀(1)行【水行】开?00赢",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "水行")

    def test_beijianliang_uses_visible_browser_block_for_bottom_window(self):
        site = next(site for site in self.sites if site.name == "北悸安涼")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "213期：【四行中特】北悸安涼",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "beijianliang-rendered",
            site.url,
            SourceKind.BROWSER,
            "213期：【四行中特】北悸安涼\n"
            "211期 四行中特 （木金土火）开马01错\n"
            "212期 四行中特 （木金水火）开牛06错\n"
            "213期 四行中特 （木土水火）开0000准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "金行")

    def test_qiluwangyang_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "歧路亡羊")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "214期歧路亡羊【绝杀一行】歧路亡羊发表于",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "qiluwangyang-rendered",
            site.url,
            SourceKind.BROWSER,
            "214期歧路亡羊【绝杀一行】歧路亡羊发表于\n"
            "214期【绝杀一行】【木行】开0000准\n"
            "213期【绝杀一行】【金行】开猴35错\n"
            "212期【绝杀一行】【土行】开牛06错",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "金行")

    def test_yaoyaohuanghuang_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "摇摇晃晃")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "214期 摇摇晃晃 【绝杀一行】 摇钱树专属",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "yaoyaohuanghuang-rendered",
            site.url,
            SourceKind.BROWSER,
            "214期 摇摇晃晃 【绝杀一行】 摇钱树专属\n"
            "214期【绝杀一行】【杀木行】开0000准\n"
            "213期【绝杀一行】【杀火行】开猴35准\n"
            "212期【绝杀一行】【杀水行】开牛06准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "火行")

    def test_yeboqinghuai_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "夜泊秦淮")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "213期:夜泊秦淮【绝杀一行】资料已公开",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "yeboqinghuai-rendered",
            site.url,
            SourceKind.BROWSER,
            "213期:夜泊秦淮【绝杀一行】资料已公开\n"
            "213期：绝杀一行【土行】开0000准\n"
            "212期：绝杀一行【木行】开牛06错\n"
            "211期：绝杀一行【水行】开马01错",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "土行")

    def test_manmianchunfeng_uses_visible_browser_block_for_bottom_window(self):
        site = next(site for site in self.sites if site.name == "满面春风")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertRegex(
            "精英贴 213期满面春风【稳杀一行】已上料",
            rule.browser_plan.required_text_pattern,
        )
        document = SourceDocument(
            "manmianchunfeng-rendered",
            site.url,
            SourceKind.BROWSER,
            "精英贴 213期满面春风【稳杀一行】已上料\n"
            "215期【稳杀一行】【木行】开0000错\n"
            "214期【稳杀一行】【火行】开牛06错\n"
            "213期【稳杀一行】【水行】开猴35准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "水行")

    def test_dadizhu_uses_browser_page_source_for_highlighted_top_window(self):
        site = next(site for site in self.sites if site.name == "大地主")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertFalse(rule.browser_plan.visible_text_only)
        document = SourceDocument(
            "dadizhu-rendered",
            site.url,
            SourceKind.BROWSER,
            '<p>【五表主四行】√</p>'
            '<p>214期【金.木.火.水】</p>'
            '<p>213期【土.<span style="background-color: #ffff00;">金</span>.木.火】</p>'
            '<p>212期【水.<span style="background-color: #ffff00;">土</span>.金.木】</p>',
            0,
            metadata=(("capture_part", "page_source"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "金行")

    def test_yishenxianqi_uses_visible_browser_block_for_bottom_window(self):
        site = next(site for site in self.sites if site.name == "一身仙气")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertIn(site.url, registry_data.BROWSER_NO_SCROLL_URLS)
        document = SourceDocument(
            "yishenxianqi-rendered",
            site.url,
            SourceKind.BROWSER,
            "一身仙气（绝杀一行）\n"
            "211期:绝杀(1)行【火行】开:马01对\n"
            "212期:绝杀(1)行【土行】开:牛06错\n"
            "213期:绝杀(1)行【火行】开:？00对",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "火行")

    def test_tianqing_runshou_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "天青润薮")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        document = SourceDocument(
            "tianqingrunshou-rendered",
            site.url,
            SourceKind.BROWSER,
            "绝杀贴214期【绝杀一行】已更新\n"
            "天青润薮 发表于 04月29日 21:25:53\n"
            "214期:绝杀一行【火行】開:0000准\n"
            "213期:绝杀一行【木行】開:猴35准\n"
            "212期:绝杀一行【水行】開:牛06准\n"
            "上一篇：绝杀贴214期【绝杀⑤码】已更新",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "木行")

    def test_huanzhugege_allows_explicit_configured_region_when_api_omits_direction(self):
        site = next(site for site in self.sites if site.name == "还珠格格")
        rule = self.registry.require(site.site_id)

        self.assertIn(site.url, registry_data.ARTICLE_API_CONFIGURED_REGION_FALLBACK_URLS)
        payload = {
            "id": "6a081678e0d076537e1df816",
            "authorNickname": "还珠格格",
            "title": base64.b64encode("213期：【绝杀一行】实力公开".encode()).decode(),
            "html": base64.b64encode(
                "213期：《还珠格格》绝杀一行【金】开:00准\n"
                "212期：《还珠格格》绝杀一行【金】开:牛06准\n"
                "211期：《还珠格格》绝杀一行【土】开:马01准"
            .encode()).decode(),
            "formSections": [{"id": "main", "name": "123", "type": "mainArticle", "sortOrder": 0}],
        }
        documents = rule.api_decoder(json.dumps(payload))
        authoritative = rule.select_authority(documents, 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "金行")

    def test_ouduansilian_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "藕断丝连")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        document = SourceDocument(
            "ouduansilian-rendered",
            site.url,
            SourceKind.BROWSER,
            "杀肖区 214期: 藕断丝连「精杀一行」\n"
            "藕断丝连 发表于 08月02日 00:20:56\n"
            "214期「精杀一行」【金】开：0000准\n"
            "213期「精杀一行」【土】开：猴35准\n"
            "212期「精杀一行」【水】开：牛06准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "土行")

    def test_jinshangtianhua_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "锦上添花")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        document = SourceDocument(
            "jinshangtianhua-rendered",
            site.url,
            SourceKind.BROWSER,
            "杀肖区 213期: 锦上添花「精杀一行」\n"
            "锦上添花 发表于 07月31日 23:55:10\n"
            "213期「精杀一行」【土】开：0000准\n"
            "212期「精杀一行」【火】开：牛06准\n"
            "211期「精杀一行」【金】开：马01准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "土行")

    def test_tixindiaodan_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "提心吊胆")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        document = SourceDocument(
            "tixindiaodan-rendered",
            site.url,
            SourceKind.BROWSER,
            "杀肖区 213期: 提心吊胆「精杀一行」\n"
            "提心吊胆 发表于 07月31日 23:55:36\n"
            "213期：▼精杀一行▼【火】开0000对\n"
            "212期：▼精杀一行▼【金】开牛06对\n"
            "211期：▼精杀一行▼【水】开马01错\n"
            "上一篇：杀肖区 213期: 风波亭里「精杀半波」",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "火行")

    def test_baofengzhouyu_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "暴风骤雨")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        self.assertIn(site.url, registry_data.BROWSER_NON_BLOCKING_LOAD_URLS)
        document = SourceDocument(
            "baofengzhouyu-rendered",
            site.url,
            SourceKind.BROWSER,
            "213期【绝杀一行】已公开\n"
            "暴风骤雨 发表于 08月01日 02:12:20\n"
            "213期：【绝杀一行】【土】开：0000准\n"
            "212期：【绝杀一行】【火】开：牛06准\n"
            "211期：【绝杀一行】【木】开：马01准\n"
            "上一篇：213期【单双四肖】已公开",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "土行")

    def test_louchenchuiying_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "镂尘吹影")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        document = SourceDocument(
            "louchenchuiying-rendered",
            site.url,
            SourceKind.BROWSER,
            "澳门醉八仙 | 财富快车 | 214期:镂尘吹影【绝杀一行】\n"
            "作者:镂尘吹影\n"
            "214期:绝杀(1)行【水行】开:00准\n"
            "213期:绝杀(1)行【水行】开:猴35准\n"
            "212期:绝杀(1)行【木行】开:牛06准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "水行")

    def test_fengyuwuzhu_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "风雨无阻")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        document = SourceDocument(
            "fengyuwuzhu-rendered",
            site.url,
            SourceKind.BROWSER,
            "高手资料213期:（绝杀一行）已上料\n"
            "风雨无阻 发表于 08月01日 02:19:33\n"
            "213期:?绝杀一行?《土》开:0000准\n"
            "212期:?绝杀一行?《火》开:牛06准\n"
            "211期:?绝杀一行?《木》开:马01准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "土行")

    def test_mimihuhu_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "迷迷糊糊")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        document = SourceDocument(
            "mimihuhu-rendered",
            site.url,
            SourceKind.BROWSER,
            "213期【绝杀一行】已公开\n"
            "迷迷糊糊 发表于 08月01日 07:24:30\n"
            "213期:【绝杀①行】【土行】开:？00赢\n"
            "212期:【绝杀①行】【金行】开:牛06赢\n"
            "211期:【绝杀①行】【水行】开:马01错\n"
            "上一篇：213期【其他资料】",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "土行")

    def test_huarongyuemao_uses_visible_browser_block_for_top_window(self):
        site = next(site for site in self.sites if site.name == "花容月貌")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        document = SourceDocument(
            "huarongyuemao-rendered",
            site.url,
            SourceKind.BROWSER,
            "214期：东方红【绝杀一行】实力造\n"
            "花容月貌 发表于 08月01日 22:19:01\n"
            "214期【绝杀一行】《木》开：？00准\n"
            "213期【绝杀一行】《火》开：猴35准\n"
            "212期【绝杀一行】《水》开：牛06准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "火行")

    def test_zhuge_shentong_uses_visible_browser_block_for_bottom_window(self):
        site = next(site for site in self.sites if site.name == "诸葛神通")
        rule = self.registry.require(site.site_id)

        self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
        self.assertTrue(rule.browser_plan.visible_text_only)
        document = SourceDocument(
            "zhugeshentong-rendered",
            site.url,
            SourceKind.BROWSER,
            "211期:『诸葛神通』 🚲四行中特🚲【火.金.水.土】开:水01准\n"
            "212期:『诸葛神通』 🚲四行中特🚲【火.金.木.土】开:土06准\n"
            "213期:『诸葛神通』 🚲四行中特🚲【火.金.水.土】开:金35准\n"
            "214期:『诸葛神通』 🚲四行中特🚲【火.金.水.土】开:00准",
            0,
            metadata=(("capture_part", "body"),),
            rendered=True,
        )
        authoritative = rule.select_authority((document,), 213)
        candidates = rule.parse(authoritative)
        decision = validate_scrape_candidates(site, 213, candidates, authoritative)

        self.assertTrue(decision.passed)
        self.assertEqual(decision.candidate.wuxing, "木行")

    def test_dynamic_rule_decodes_api_and_parser_keeps_record_provenance(self):
        site = next(site for site in self.sites if site.name == "典则俊雅")
        rule = self.registry.require(site.site_id)
        payload = {
            "data": {
                "id": "6a20da1dca6da63e15d01fc8",
                "authorNickname": "典则俊雅",
                "title": base64.b64encode("典则俊雅".encode()).decode(),
                "html": base64.b64encode("209期『典则俊雅』绝杀一行【木行】".encode()).decode(),
                "formSections": [{"type": "mainArticle", "name": "主文章"}],
                "direction": "bottom",
            }
        }

        documents = rule.api_decoder(json.dumps(payload))

        self.assertEqual(documents[0].source_kind, SourceKind.API)
        self.assertEqual(documents[0].record_id, "6a20da1dca6da63e15d01fc8")
        candidates = rule.parse(documents)
        self.assertEqual([(item.period, item.wuxing, item.record_id) for item in candidates], [(209, "木行", documents[0].record_id)])

    def test_same_document_nested_text_echo_is_preserved_for_validation(self):
        site = next(site for site in self.sites if site.name == "八级心动")
        rule = self.registry.require(site.site_id)
        document = SourceDocument(
            "browser-fixture",
            site.url,
            SourceKind.BROWSER,
            "211期；绝杀一行：（木）开；\n211期；绝杀一行：（木）开；马01中",
            0,
        )
        candidates = tuple(item for item in rule.parse((document,)) if item.period == 211)
        self.assertEqual(len(candidates), 2)

    def test_spa_authority_uses_primary_user_record(self):
        site = next(site for site in self.sites if site.name == "随便项链")
        rule = self.registry.require(site.site_id)
        first = SourceDocument("spa-1", site.url, SourceKind.SPA, "[SPA_STRUCTURED_USER_RECORD]\n210期绝杀一行【金行】", 0, record_id="one")
        second = SourceDocument("spa-2", site.url, SourceKind.SPA, "[SPA_STRUCTURED_USER_RECORD]\n211期绝杀一行【木行】", 1, record_id="two")
        selected = rule.select_authority((first, second), 211)
        self.assertEqual(tuple(item.document_id for item in selected), ("spa-2",))

    def test_spa_overlapping_history_deduplicates_exact_candidate_echoes(self):
        site = next(site for site in self.sites if site.name == "随便项链")
        rule = self.registry.require(site.site_id)
        first = SourceDocument(
            "spa-1",
            site.url,
            SourceKind.SPA,
            "[SPA_STRUCTURED_USER_RECORD]\n213期绝杀一行【金行】",
            0,
            record_id="one",
        )
        second = SourceDocument(
            "spa-2",
            site.url,
            SourceKind.SPA,
            "[SPA_STRUCTURED_USER_RECORD]\n213期绝杀一行【金行】",
            1,
            record_id="two",
        )

        candidates = tuple(item for item in rule.parse((first, second)) if item.period == 213)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].source_document_id, "spa-1")

    def test_spa_overlapping_history_keeps_different_candidate_values(self):
        site = next(site for site in self.sites if site.name == "随便项链")
        rule = self.registry.require(site.site_id)
        first = SourceDocument(
            "spa-1",
            site.url,
            SourceKind.SPA,
            "[SPA_STRUCTURED_USER_RECORD]\n213期绝杀一行【金行】",
            0,
            record_id="one",
        )
        second = SourceDocument(
            "spa-2",
            site.url,
            SourceKind.SPA,
            "[SPA_STRUCTURED_USER_RECORD]\n213期绝杀一行【木行】",
            1,
            record_id="two",
        )

        candidates = tuple(item for item in rule.parse((first, second)) if item.period == 213)

        self.assertEqual({item.wuxing for item in candidates}, {"金行", "木行"})

    def test_chunmanxiangcun_dot_anchor_is_preserved(self):
        site = next(site for site in self.sites if site.name == "春满乡村")
        rule = self.registry.require(site.site_id)
        document = SourceDocument(
            "chunman-fixture",
            site.url,
            SourceKind.PAGE,
            "春满乡村（绝杀1.行）\n213期绝杀1.行【金金金】",
            0,
        )

        candidates = rule.parse((document,))

        self.assertEqual([(item.period, item.wuxing, item.anchor) for item in candidates], [(213, "金行", "绝杀1.行")])

    def test_authority_does_not_join_independent_documents(self):
        site = next(site for site in self.sites if site.name == "信封论坛")
        rule = self.registry.require(site.site_id)
        title = SourceDocument(
            "title-doc",
            site.url,
            SourceKind.PAGE,
            "澳门信封论坛 绝杀一行",
            0,
        )
        rows = SourceDocument(
            "row-doc",
            site.url,
            SourceKind.SCRIPT,
            "211期：[绝杀一行] [木行]",
            1,
            parent_document_id=title.document_id,
        )

        selected = rule.select_authority((title, rows), 211)

        self.assertNotIn("\n".join((title.text, rows.text)), {item.text for item in selected})
        self.assertTrue(all(item.document_id in {title.document_id, rows.document_id} for item in selected))

    def test_bajixindong_uses_visible_text_boundary(self):
        site = next(site for site in self.sites if site.name == "八级心动")
        rule = self.registry.require(site.site_id)
        self.assertTrue(rule.browser_plan.visible_text_only)
        document = SourceDocument(
            "browser-visible-boundary",
            site.url,
            SourceKind.BROWSER,
            "八级心动 绝杀一行\n211期绝杀一行【土行】开马01准",
            0,
        )
        candidates = [candidate for candidate in rule.parse((document,)) if candidate.period == 211]
        self.assertEqual([(candidate.wuxing, candidate.raw) for candidate in candidates], [("土行", "211期绝杀一行【土行】开马01准")])

    def test_bajixindong_keeps_ocr_conflict_for_shared_validator(self):
        site = next(site for site in self.sites if site.name == "八级心动")
        rule = self.registry.require(site.site_id)
        document = SourceDocument(
            "browser-ocr-conflict",
            site.url,
            SourceKind.BROWSER,
            "八级心动 绝杀一行\n211期绝杀一行【木行】开马01准\n土行 211期 八级心动",
            0,
        )
        values = {
            candidate.wuxing
            for candidate in rule.parse((document,))
            if candidate.period == 211
        }
        self.assertEqual(values, {"木行", "土行"})


if __name__ == "__main__":
    unittest.main()
