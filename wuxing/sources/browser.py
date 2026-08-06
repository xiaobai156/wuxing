from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Protocol
from urllib.parse import urljoin, urlparse

from wuxing.domain.enums import SourceKind
from wuxing.domain.errors import FetchError
from wuxing.domain.models import SiteConfig, SourceDocument
from wuxing import registry_data

from .article_api import ARTICLE_ID_TOKEN_RE, article_id_from_url, is_article_detail_url, require_article_id
from .ocr import validate_ocr_entries
from .spa import spa_user_id_from_url


PERIOD_RE = re.compile(r"(?<!\d)(\d{1,4})\s*期")
ARTICLE_TARGET_RE = re.compile(
    r"(?:绝杀|必杀|精杀|稳杀|死禁|殺|杀)\s*[（(]?\s*[一1①➀⑴㈠⒈]\s*[)）]?\s*行"
    r"|[一二三四五①②③④⑤\d]\s*行\s*中\s*特"
)


@dataclass(frozen=True)
class BrowserPlan:
    tab_label_pattern: str = ""
    click_text_pattern: str = ""
    exact_click_path: str = ""
    popup_close_selector: str = ""
    required_text_pattern: str = ""
    visible_text_only: bool = False
    ocr_script: str = ""
    record_selector: str = ""


@dataclass(frozen=True)
class BrowserCapture:
    current_url: str
    page_source: str
    body_text: str
    record_id: str | None = None
    record_text: str = ""
    record_html: str = ""
    ocr_entries: tuple[object, ...] = ()


class BrowserBackend(Protocol):
    def capture(
        self,
        site: SiteConfig,
        period: int,
        timeout: int,
        show_browser: bool,
        plan: BrowserPlan,
    ) -> BrowserCapture: ...


class BrowserSource:
    def __init__(self, backend: BrowserBackend):
        self.backend = backend

    def fetch(
        self,
        site: SiteConfig,
        period: int,
        timeout: int,
        show_browser: bool,
        plan: BrowserPlan | None = None,
    ) -> tuple[SourceDocument, ...]:
        resolved_plan = plan or BrowserPlan()
        capture = self.backend.capture(site, period, timeout, show_browser, resolved_plan)
        self._validate_boundary(site, capture, resolved_plan)
        ocr_lines = validate_ocr_entries(capture.ocr_entries, period)
        if capture.ocr_entries and not ocr_lines:
            raise FetchError("OCR独立期号或五行二次校验未通过")
        record_id = article_id_from_url(site.url) or spa_user_id_from_url(site.url)
        documents: list[SourceDocument] = []
        if is_article_detail_url(site.url):
            expected_article_id = require_article_id(site.url, "article页面")
            documents.append(SourceDocument(
                document_id=f"browser-{site.site_id}-{period}-record",
                url=capture.current_url,
                source_kind=SourceKind.BROWSER,
                text=capture.record_text,
                order=0,
                record_id=expected_article_id,
                rendered=True,
                metadata=(
                    ("capture_part", "record"),
                    ("record_scope", "exact"),
                    ("record_id_evidence", "dom_exact"),
                ),
            ))
            return tuple(documents)
        if capture.page_source:
            documents.append(SourceDocument(
                document_id=f"browser-{site.site_id}-{period}-page-source",
                url=capture.current_url,
                source_kind=SourceKind.BROWSER,
                text=capture.page_source,
                order=0,
                record_id=record_id,
                rendered=True,
                metadata=(("capture_part", "page_source"),),
            ))
        if capture.body_text:
            documents.append(SourceDocument(
                document_id=f"browser-{site.site_id}-{period}-body",
                url=capture.current_url,
                source_kind=SourceKind.BROWSER,
                text=capture.body_text,
                order=1,
                record_id=record_id,
                rendered=True,
                metadata=(("capture_part", "body"),),
            ))
        if ocr_lines:
            ocr_text = "\n".join(f"{site.name} 绝杀一行 {line}" for line in ocr_lines)
            documents.append(SourceDocument(
                document_id=f"browser-{site.site_id}-{period}-ocr",
                url=capture.current_url,
                source_kind=SourceKind.OCR,
                text=ocr_text,
                order=2,
                parent_document_id=f"browser-{site.site_id}-{period}-body",
                record_id=record_id,
                rendered=True,
                metadata=(("capture_part", "ocr"), ("validated", "true")),
            ))
        if not documents:
            raise FetchError("浏览器页面正文为空")
        return tuple(documents)

    @staticmethod
    def _validate_boundary(site: SiteConfig, capture: BrowserCapture, plan: BrowserPlan) -> None:
        expected_article_id = article_id_from_url(site.url)
        scope_text = capture.body_text
        if is_article_detail_url(site.url):
            expected_article_id = require_article_id(site.url, "article页面")
            current_id = article_id_from_url(capture.current_url)
            if current_id != expected_article_id:
                raise FetchError(
                    f"浏览器文章ID不一致：当前={current_id or '缺失'} 目标={expected_article_id}"
                )
            if expected_article_id not in capture.page_source:
                raise FetchError(f"浏览器页面未包含目标文章ID {expected_article_id}")
            if capture.record_id != expected_article_id or not capture.record_text.strip():
                raise FetchError("浏览器页面未提供唯一目标记录正文，拒绝解析")
            scope_text = capture.record_text
            nested_record_ids = set(ARTICLE_ID_TOKEN_RE.findall(scope_text)) - {expected_article_id}
            if nested_record_ids:
                raise FetchError(
                    f"浏览器目标记录正文包含其他文章ID：{'、'.join(sorted(nested_record_ids))}"
                )
            if site.name not in scope_text:
                raise FetchError("浏览器目标记录作者不匹配")
            if not plan.required_text_pattern and not ARTICLE_TARGET_RE.search(scope_text):
                raise FetchError("浏览器动态文章缺少目标栏目锚点")
        if plan.required_text_pattern and not re.search(plan.required_text_pattern, scope_text):
            raise FetchError(f"浏览器页面缺少专属锚点：{plan.required_text_pattern}")
        expected_user_id = spa_user_id_from_url(site.url)
        if expected_user_id:
            current_user_id = spa_user_id_from_url(capture.current_url)
            if current_user_id != expected_user_id:
                raise FetchError(
                    f"SPA浏览器用户ID不一致：当前={current_user_id or '缺失'} 目标={expected_user_id}"
                )


class SeleniumBrowserBackend:
    """Selenium transport only; site-specific interaction comes from BrowserPlan."""

    def capture(
        self,
        site: SiteConfig,
        period: int,
        timeout: int,
        show_browser: bool,
        plan: BrowserPlan,
    ) -> BrowserCapture:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
        except Exception as exc:
            raise FetchError(f"浏览器依赖不可用：{exc}") from exc

        options = Options()
        if not show_browser:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--window-size=1280,1800")

        try:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        except Exception:
            driver = webdriver.Chrome(options=options)
        try:
            driver.set_page_load_timeout(timeout)
            try:
                driver.get(site.url)
            except Exception as exc:
                message = str(exc).lower()
                if (
                    site.url not in registry_data.BROWSER_NON_BLOCKING_LOAD_URLS
                    or "missing or invalid columnnumber" not in message
                ):
                    raise
            WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            if plan.popup_close_selector:
                self._dismiss_popup(driver, plan.popup_close_selector, timeout)
            if site.url not in registry_data.BROWSER_NO_SCROLL_URLS:
                self._scroll(driver)
            if plan.tab_label_pattern:
                self._click_unique_text(driver, plan.tab_label_pattern, timeout)
            if plan.exact_click_path:
                self._click_exact_path(driver, site.url, plan.exact_click_path, timeout)
            elif plan.click_text_pattern:
                self._click_unique_text(driver, plan.click_text_pattern, timeout, required_period=period)
            WebDriverWait(driver, timeout).until(
                lambda current: f"{period}期" in current.find_element(By.TAG_NAME, "body").text
            )
            if site.url not in registry_data.BROWSER_NO_SCROLL_URLS:
                self._scroll(driver)
            record_scope = self._extract_record_scope(driver, site, plan)
            ocr_entries = ()
            if plan.ocr_script:
                try:
                    ocr_entries = tuple(driver.execute_script(plan.ocr_script, period) or ())
                except Exception as exc:
                    raise FetchError(f"浏览器 OCR 脚本执行失败：{type(exc).__name__}: {exc}") from exc
            return BrowserCapture(
                current_url=getattr(driver, "current_url", site.url),
                page_source=driver.page_source,
                body_text=driver.find_element(By.TAG_NAME, "body").text,
                record_id=record_scope.get("record_id") if record_scope else None,
                record_text=record_scope.get("text", "") if record_scope else "",
                record_html=record_scope.get("html", "") if record_scope else "",
                ocr_entries=ocr_entries,
            )
        except FetchError:
            raise
        except Exception as exc:
            raise FetchError(f"浏览器抓取失败：{type(exc).__name__}: {exc}") from exc
        finally:
            driver.quit()

    @staticmethod
    def _click_unique_text(driver, pattern: str, timeout: int, required_period: int | None = None) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        regex = re.compile(pattern)
        elements = driver.find_elements(
            By.CSS_SELECTOR,
            "a, button, [role='link'], [role='tab'], li, div.swiper-slide",
        )
        matches = []
        for element in elements:
            text = re.sub(r"\s+", " ", getattr(element, "text", "")).strip()
            if required_period is not None:
                periods = {int(match.group(1)) for match in PERIOD_RE.finditer(text)}
                if periods != {required_period}:
                    continue
            if regex.search(text):
                matches.append(element)
        if len(matches) != 1:
            raise FetchError(f"浏览器点击目标不唯一：找到{len(matches)}条")
        target = matches[0]
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            target,
        )
        try:
            target.click()
        except Exception:
            driver.execute_script("arguments[0].click()", target)
        WebDriverWait(driver, timeout).until(lambda current: current.find_element(By.TAG_NAME, "body"))

    @staticmethod
    def _dismiss_popup(driver, selector: str, timeout: int) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        visible = [element for element in elements if element.is_displayed()]
        if len(visible) > 1:
            raise FetchError(f"浏览器弹窗关闭目标不唯一：找到{len(visible)}条")
        if not visible:
            return
        target = visible[0]
        try:
            target.click()
        except Exception:
            driver.execute_script("arguments[0].click()", target)

        def is_hidden(_driver) -> bool:
            try:
                return not target.is_displayed()
            except Exception:
                return True

        WebDriverWait(driver, timeout).until(is_hidden)

    @staticmethod
    def _click_exact_path(driver, base_url: str, path: str, timeout: int) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        matches = [
            element for element in driver.find_elements(By.CSS_SELECTOR, "a[href]")
            if urlparse(element.get_attribute("href") or "").path == path
        ]
        if len(matches) != 1:
            raise FetchError(f"浏览器精确链接{path}不唯一：找到{len(matches)}条")
        driver.get(urljoin(base_url, matches[0].get_attribute("href")))
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    @staticmethod
    def _extract_record_scope(driver, site: SiteConfig, plan: BrowserPlan) -> dict[str, str] | None:
        expected_id = article_id_from_url(site.url)
        if not expected_id:
            return None
        result = driver.execute_script(
            """
            const expected = arguments[0];
            const customSelector = arguments[1] || "";
            const selectors = new Set();
            if (customSelector) selectors.add(customSelector.replaceAll("{id}", expected));
            selectors.add(`#${expected}`);
            for (const attr of ["data-id", "data-article-id", "data-record-id", "data-articleid"]) {
              selectors.add(`[${attr}="${expected}"]`);
            }
            const nodes = new Set();
            for (const selector of selectors) {
              try {
                for (const node of document.querySelectorAll(selector)) nodes.add(node);
              } catch (_) {}
            }
            if (nodes.size !== 1) return {count: nodes.size, record_id: "", text: "", html: ""};
            const node = [...nodes][0];
            const values = [node.id, node.getAttribute("data-id"), node.getAttribute("data-article-id"),
              node.getAttribute("data-record-id"), node.getAttribute("data-articleid")].filter(Boolean);
            if (!values.includes(expected)) return {count: 0, record_id: "", text: "", html: ""};
            const nestedIds = new Set();
            for (const child of node.querySelectorAll("[id], [data-id], [data-article-id], [data-record-id], [data-articleid]")) {
              for (const value of [child.id, child.getAttribute("data-id"), child.getAttribute("data-article-id"),
                child.getAttribute("data-record-id"), child.getAttribute("data-articleid")]) {
                if (/^[0-9a-fA-F]{24}$/.test(value || "") && value !== expected) nestedIds.add(value);
              }
            }
            if (nestedIds.size) return {count: 0, record_id: "", text: "", html: ""};
            return {
              count: 1,
              record_id: expected,
              text: node.innerText || node.textContent || "",
              html: node.outerHTML || ""
            };
            """,
            expected_id,
            plan.record_selector,
        )
        if not isinstance(result, dict) or result.get("count") != 1:
            return None
        return result

    @staticmethod
    def _scroll(driver) -> None:
        last_height = -1
        stable = 0
        for _ in range(8):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.8)
            height = int(driver.execute_script("return document.body.scrollHeight") or 0)
            if height <= last_height:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
                last_height = height
