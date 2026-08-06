import unittest

from wuxing.config.site_loader import load_site_configs
from wuxing.domain.enums import FetchStrategy
from wuxing.registry import build_site_registry


REPAIRED_TOPIC_URLS = frozenset({
    "https://jjlachsn.4fk3e-i2rpf-vgknlh.work:16677/topic/660782.html",
    "https://gboqrz.1grys-bnkqq-evlqkb.work/topic/507999.html",
    "https://jnf52f.mjhbr-zqt9a-ofmjce.work/topic/488506.html",
    "https://ezovboxw.uomne-2a0nc-yjyzjh.xyz:16677/topic/320728.html",
    "https://v0uer.e2xs0-3tuvc-rsgtzx.xyz/topic/255638.html",
    "https://nxtoep.9at21-abkka-svfjrm.xyz:16677/topic/547559.html",
    "https://xjohxjqz.s5luy-wevrh-gnxone.xyz:16677/topic/247280.html",
    "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626030.html",
    "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/625515.html",
    "https://sgxozo.4b5jw-x2zou-ukbybu.xyz:16677/topic/267706.html",
})


class TopicBrowserFirstRegressionTests(unittest.TestCase):
    def test_repaired_topic_sites_use_browser_first_and_new_rule_version(self):
        sites = load_site_configs("migration/sites.v2.preview.json")
        registry = build_site_registry(sites)

        for url in REPAIRED_TOPIC_URLS:
            with self.subTest(url=url):
                site = next(site for site in sites if site.url == url)
                rule = registry.require(site.site_id)
                self.assertIs(rule.fetch_strategy, FetchStrategy.BROWSER_FIRST)
                self.assertEqual(site.config_version, 2)

    def test_unrelated_http_topic_site_keeps_http_then_browser_strategy(self):
        sites = load_site_configs("migration/sites.v2.preview.json")
        registry = build_site_registry(sites)
        site = next(
            site
            for site in sites
            if "/topic/" in site.url
            and site.url not in REPAIRED_TOPIC_URLS
            and not site.api_url
            and registry.require(site.site_id).fetch_strategy is FetchStrategy.HTTP_THEN_BROWSER
        )

        self.assertIs(
            registry.require(site.site_id).fetch_strategy,
            FetchStrategy.HTTP_THEN_BROWSER,
        )


if __name__ == "__main__":
    unittest.main()
