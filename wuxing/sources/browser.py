from __future__ import annotations

import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qs, urljoin, urlparse

from wuxing import registry_data
from wuxing.domain.enums import SourceKind
from wuxing.domain.errors import FetchError
from wuxing.domain.models import SiteConfig, SourceDocument

from .article_api import (
    ARTICLE_ID_TOKEN_RE,
    article_id_from_url,
    is_article_detail_url,
    require_article_id,
)
from .ocr import recognize_paddle_ocr_images, validate_ocr_entries
from .spa import spa_user_id_from_url

PERIOD_RE = re.compile(r"(?<!\d)(\d{1,4})\s*期")
HIJACK_GATE_RE = re.compile(r"安全检测|正在适配|适配最优线路|请稍等|线路检测")
ARTICLE_TARGET_RE = re.compile(
    r"(?:绝杀|必杀|精杀|稳杀|死禁|殺|杀)\s*[（(]?\s*[一1①➀⑴㈠⒈]\s*[)）]?\s*行"
    r"|[一二三四五①②③④⑤\d]\s*行\s*中\s*特"
)


def view_record_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.path.rstrip("/") != "/view.php":
        return None
    values = parse_qs(parsed.query).get("id", [])
    return values[0] if len(values) == 1 and values[0].isdigit() else None

PLAYWRIGHT_INSTALL_HINT = (
    "请执行以下命令安装浏览器依赖：\n"
    "py -3.10 -m pip install -r requirements-playwright.txt\n"
    "py -3.10 -m playwright install chromium\n"
    "或运行项目现有的 安装Playwright-Chromium.bat"
)


def _playwright_dependency_message(exc: Exception) -> str:
    return f"浏览器依赖不可用：{type(exc).__name__}: {exc}\n{PLAYWRIGHT_INSTALL_HINT}"


def _load_sync_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise FetchError(_playwright_dependency_message(exc)) from exc
    return sync_playwright


@contextmanager
def _playwright_runtime(sync_playwright):
    entered = False
    try:
        with sync_playwright() as playwright:
            entered = True
            yield playwright
    except Exception as exc:
        if not entered:
            raise FetchError(_playwright_dependency_message(exc)) from exc
        raise


@dataclass(frozen=True)
class BrowserPlan:
    tab_label_pattern: str = ""
    click_text_pattern: str = ""
    exact_click_path: str = ""
    popup_close_selector: str = ""
    required_text_pattern: str = ""
    visible_text_only: bool = False
    ocr_enabled: bool = False
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
        if resolved_plan.record_selector:
            if not capture.record_text.strip():
                raise FetchError("浏览器页面未提供唯一专属正文容器，拒绝解析")
            documents.append(SourceDocument(
                document_id=f"browser-{site.site_id}-{period}-record",
                url=capture.current_url,
                source_kind=SourceKind.BROWSER,
                text=(
                    capture.record_text
                    if resolved_plan.visible_text_only
                    else capture.record_html or capture.record_text
                ),
                order=0,
                rendered=True,
                metadata=(
                    ("capture_part", "record"),
                    ("record_scope", "exact"),
                    ("record_selector", resolved_plan.record_selector),
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
            # 只放 OCR 识别到的原始行，不注入站名和栏目词：
            # 注入会让 keyword 校验对 OCR 文档恒成立，等于绕过栏目证明。
            ocr_text = "\n".join(ocr_lines)
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
        elif plan.record_selector:
            if not capture.record_text.strip():
                raise FetchError("浏览器页面未提供唯一专属正文容器，拒绝解析")
            scope_text = capture.record_text
        expected_view_id = view_record_id_from_url(site.url)
        if expected_view_id:
            current_view_id = view_record_id_from_url(capture.current_url)
            if current_view_id != expected_view_id:
                raise FetchError(
                    f"浏览器记录ID不一致：当前={current_view_id or '缺失'} 目标={expected_view_id}"
                )
        if plan.required_text_pattern and not re.search(plan.required_text_pattern, scope_text):
            raise FetchError(f"浏览器页面缺少专属锚点：{plan.required_text_pattern}")
        expected_user_id = spa_user_id_from_url(site.url)
        if expected_user_id:
            current_user_id = spa_user_id_from_url(capture.current_url)
            if current_user_id != expected_user_id:
                raise FetchError(
                    f"SPA浏览器用户ID不一致：当前={current_user_id or '缺失'} 目标={expected_user_id}"
                )


class PlaywrightBrowserBackend:
    """Playwright transport only; site-specific interaction comes from BrowserPlan."""

    def capture(
        self,
        site: SiteConfig,
        period: int,
        timeout: int,
        show_browser: bool,
        plan: BrowserPlan,
    ) -> BrowserCapture:
        sync_playwright = _load_sync_playwright()
        timeout_ms = max(1, int(timeout * 1000))
        try:
            with _playwright_runtime(sync_playwright) as playwright:
                browser = None
                context = None
                page = None
                try:
                    try:
                        launch_options: dict[str, object] = {"headless": not show_browser}
                        if site.browser_channel:
                            launch_options["channel"] = site.browser_channel
                        browser = playwright.chromium.launch(**launch_options)
                    except Exception as exc:
                        raise FetchError(_playwright_dependency_message(exc)) from exc
                    context = browser.new_context(
                        ignore_https_errors=True,
                        viewport={"width": 1280, "height": 1800},
                    )
                    page = context.new_page()
                    page.goto(
                        site.url,
                        wait_until=self._wait_until(site.url),
                        timeout=timeout_ms,
                    )
                    body = page.locator("body")
                    body.wait_for(state="attached", timeout=timeout_ms)
                    page = self._escape_hijack_gate(page, site, timeout_ms, context, browser)
                    body = page.locator("body")
                    body.wait_for(state="attached", timeout=timeout_ms)
                    if plan.popup_close_selector:
                        self._dismiss_popup(page, plan.popup_close_selector, timeout_ms)
                    if site.url not in registry_data.BROWSER_NO_SCROLL_URLS:
                        self._scroll(page)
                    if plan.tab_label_pattern:
                        self._click_unique_text(page, plan.tab_label_pattern, timeout_ms)
                    if plan.exact_click_path:
                        self._click_exact_path(page, site.url, plan.exact_click_path, timeout_ms)
                    elif plan.click_text_pattern:
                        self._click_unique_text(page, plan.click_text_pattern, timeout_ms, required_period=period)
                    page.wait_for_function(
                        "period => Boolean(document.body && document.body.innerText.includes(String(period) + '期'))",
                        arg=period,
                        timeout=timeout_ms,
                    )
                    if site.url not in registry_data.BROWSER_NO_SCROLL_URLS:
                        self._scroll(page)
                    if is_article_detail_url(site.url):
                        record_scope = self._extract_record_scope(page, site, plan)
                    else:
                        record_scope = self._extract_unique_content_scope(page, plan)
                    ocr_entries = ()
                    if plan.ocr_enabled and period is not None:
                        ocr_entries = self._capture_ocr_entries(page, period, timeout_ms)
                    return BrowserCapture(
                        current_url=page.url or site.url,
                        page_source=page.content(),
                        body_text=body.inner_text(),
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
                    self._close_quietly(page)
                    self._close_quietly(context)
                    self._close_quietly(browser)
        except FetchError:
            raise
        except Exception as exc:
            raise FetchError(f"浏览器抓取失败：{type(exc).__name__}: {exc}") from exc

    @staticmethod
    def _capture_ocr_entries(page, target_period: int | None, timeout_ms: int) -> tuple[object, ...]:
        images = page.locator("img")
        eligible: list[tuple[float, int, object]] = []
        try:
            image_count = images.count()
        except Exception as exc:
            raise FetchError(f"浏览器 OCR 阶段枚举图片失败：{type(exc).__name__}: {exc}") from exc
        for index in range(image_count):
            image = images.nth(index)
            try:
                if not image.is_visible():
                    continue
                dimensions = image.evaluate(
                    "image => ({naturalWidth: image.naturalWidth, naturalHeight: image.naturalHeight})"
                )
                natural_width = int(dimensions.get("naturalWidth", 0))
                natural_height = int(dimensions.get("naturalHeight", 0))
                if natural_width <= 700 or natural_height <= 900:
                    continue
                box = image.bounding_box()
                if not box or "y" not in box:
                    raise FetchError(f"浏览器 OCR 阶段无法获取符合尺寸图片的位置（第{index + 1}张）")
                eligible.append((float(box["y"]), index, image))
            except FetchError:
                raise
            except Exception as exc:
                raise FetchError(
                    f"浏览器 OCR 阶段检查图片失败（第{index + 1}张）：{type(exc).__name__}: {exc}"
                ) from exc

        if not eligible:
            return ()

        screenshots: list[bytes] = []
        for image_number, (_, _, image) in enumerate(sorted(eligible, key=lambda item: (item[0], item[1])), start=1):
            try:
                screenshots.append(image.screenshot(type="png", timeout=timeout_ms))
            except Exception as exc:
                raise FetchError(
                    f"浏览器 OCR 阶段图片截图失败（第{image_number}张）：{type(exc).__name__}: {exc}"
                ) from exc
        try:
            return tuple(recognize_paddle_ocr_images(screenshots, target_period))
        except Exception as exc:
            raise FetchError(
                f"浏览器 OCR 阶段 PaddleOCR 识别失败：{type(exc).__name__}: {exc}"
            ) from exc

    @staticmethod
    def _wait_until(url: str) -> str:
        return "commit" if url in registry_data.BROWSER_NON_BLOCKING_LOAD_URLS else "load"

    @staticmethod
    def _is_hijack_gate(body_text: str) -> bool:
        """识别「安全检测/线路适配」劫持过渡页；此类页面不含任何文章正文。"""
        return len(body_text.strip()) < 200 and HIJACK_GATE_RE.search(body_text) is not None

    def _escape_hijack_gate(self, page, site: SiteConfig, timeout_ms: int, context, browser):
        """域名被劫持时，等过渡页放行后按落地域名重建原文章路径，回到同一篇文章。

        只重建 path（文章 ID 仍在 URL 中），不跨站、不换文章、不补值；
        若重建后仍取不到原文章，则原样返回，交由后续统一校验判失败。
        """
        try:
            if not self._is_hijack_gate(page.inner_text("body")):
                return page
        except Exception:
            return page
        original = urlparse(site.url)
        deadline = time.time() + max(20.0, timeout_ms / 1000.0)
        landed = page
        while time.time() < deadline:
            time.sleep(2)
            try:
                if not self._is_hijack_gate(landed.inner_text("body")):
                    break
            except Exception:
                pass
        landed_parts = urlparse(landed.url)
        if not landed_parts.netloc or landed_parts.netloc == original.netloc:
            return landed
        rebuilt = f"{landed_parts.scheme}://{landed_parts.netloc}{original.path}"
        if original.query:
            rebuilt = f"{rebuilt}?{original.query}"
        candidate = context.new_page()
        try:
            candidate.goto(rebuilt, wait_until=self._wait_until(rebuilt), timeout=timeout_ms)
            candidate.locator("body").wait_for(state="attached", timeout=timeout_ms)
            # 换域只允许「同一文章路径」：落地 URL 必须仍带原 path，且页面正文要能证明是本站，
            # 否则视为串站，回退原页交由统一校验判失败。
            settled = urlparse(candidate.url)
            path_kept = settled.path.rstrip("/") == original.path.rstrip("/")
            try:
                body_text = candidate.inner_text("body")
            except Exception:
                body_text = ""
            identity_ok = bool(site.name) and site.name in body_text
            if not path_kept or not identity_ok:
                self._close_quietly(candidate)
                return landed
            self._close_quietly(landed)
            return candidate
        except Exception:
            self._close_quietly(candidate)
            return landed

    @staticmethod
    def _close_quietly(resource) -> None:
        if resource is None:
            return
        try:
            resource.close()
        except Exception:
            pass

    @staticmethod
    def _click_unique_text(page, pattern: str, timeout_ms: int, required_period: int | None = None) -> None:
        regex = re.compile(pattern)
        elements = page.locator("a, button, [role='link'], [role='tab'], li, div.swiper-slide")
        matches = []
        for index in range(elements.count()):
            element = elements.nth(index)
            if not element.is_visible():
                continue
            text = re.sub(r"\s+", " ", element.inner_text()).strip()
            if required_period is not None:
                periods = {int(match.group(1)) for match in PERIOD_RE.finditer(text)}
                if periods != {required_period}:
                    continue
            if regex.search(text):
                matches.append(element)
        if len(matches) != 1:
            raise FetchError(f"浏览器点击目标不唯一：找到{len(matches)}条")
        target = matches[0]
        target.scroll_into_view_if_needed(timeout=timeout_ms)
        target.click(timeout=timeout_ms)
        page.locator("body").wait_for(state="attached", timeout=timeout_ms)

    @staticmethod
    def _dismiss_popup(page, selector: str, timeout_ms: int) -> None:
        elements = page.locator(selector)
        visible = [elements.nth(index) for index in range(elements.count()) if elements.nth(index).is_visible()]
        if len(visible) > 1:
            raise FetchError(f"浏览器弹窗关闭目标不唯一：找到{len(visible)}条")
        if not visible:
            return
        target = visible[0]
        target.click(timeout=timeout_ms)
        target.wait_for(state="hidden", timeout=timeout_ms)

    @staticmethod
    def _click_exact_path(page, base_url: str, path: str, timeout_ms: int) -> None:
        links = page.locator("a[href]")
        matches = []
        for index in range(links.count()):
            target = links.nth(index)
            if urlparse(target.get_attribute("href") or "").path == path:
                matches.append(target)
        if len(matches) != 1:
            raise FetchError(f"浏览器精确链接{path}不唯一：找到{len(matches)}条")
        page.goto(
            urljoin(base_url, matches[0].get_attribute("href") or ""),
            wait_until=PlaywrightBrowserBackend._wait_until(base_url),
            timeout=timeout_ms,
        )
        page.locator("body").wait_for(state="attached", timeout=timeout_ms)

    @staticmethod
    def _extract_record_scope(page, site: SiteConfig, plan: BrowserPlan) -> dict[str, str] | None:
        expected_id = article_id_from_url(site.url)
        if not expected_id:
            return None
        result = page.evaluate(
            """
            args => {
              const {expected, customSelector} = args;
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
            }
            """,
            {"expected": expected_id, "customSelector": plan.record_selector},
        )
        if not isinstance(result, dict) or result.get("count") != 1:
            return None
        return result

    @staticmethod
    def _extract_unique_content_scope(page, plan: BrowserPlan) -> dict[str, str] | None:
        if not plan.record_selector:
            return None
        elements = page.locator(plan.record_selector)
        matches = []
        for index in range(elements.count()):
            element = elements.nth(index)
            if not element.is_visible():
                continue
            text = element.inner_text()
            if plan.required_text_pattern and not re.search(plan.required_text_pattern, text):
                continue
            matches.append((element, text))
        if len(matches) != 1:
            raise FetchError(
                f"浏览器专属正文容器不唯一：选择器={plan.record_selector} 找到{len(matches)}条"
            )
        element, text = matches[0]
        return {
            "record_id": "",
            "text": text,
            "html": element.evaluate("node => node.outerHTML || ''"),
        }

    @staticmethod
    def _scroll(page) -> None:
        last_height = -1
        stable = 0
        for _ in range(8):
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)", None)
            time.sleep(0.8)
            height = int(page.evaluate("() => document.body.scrollHeight", None) or 0)
            if height <= last_height:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
                last_height = height
