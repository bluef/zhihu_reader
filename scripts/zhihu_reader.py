#!/usr/bin/env python3
"""
Unified Zhihu page reader.

Capabilities:
- question page
- answer page
- article page
- fallback to HTML/debug saving when content extraction fails
- fallback to requests when Playwright browser is unavailable
"""
import asyncio
import json
import sys
from pathlib import Path

import requests
from playwright.async_api import async_playwright

OUT_DIR = Path('/root/.openclaw/workspace/skills/zhihu-page-reader/out')
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)

QUESTION_SELECTORS = [
    '.Question-main',
    '.QuestionHeader',
    '.QuestionHeader-content',
    '.Question-mainColumn',
    '[data-za-detail-view-path-module="QuestionItem"]',
]

ANSWER_SELECTORS = [
    '.AnswerItem',
    '.Answer',
    '.ContentItem-answer',
    '.RichContent-inner',
]

ARTICLE_SELECTORS = [
    '.Post-RichTextContainer',
    '.RichText',
    '.ztext',
    'article',
    '.Post-content',
]


def classify_url(url: str) -> str:
    if '/answer/' in url:
        return 'answer'
    if '/question/' in url:
        return 'question'
    if 'zhuanlan.zhihu.com/p/' in url:
        return 'article'
    return 'unknown'


def extract_text_from_html(html: str, selectors):
    for selector in selectors:
        if selector.replace('.', '') in html:
            return selector, html[:8000]
    return None, None


async def collect_answers(page):
    answers = []
    nodes = await page.query_selector_all('.AnswerItem, .Answer, .ContentItem-answer')
    for idx, node in enumerate(nodes[:20]):
        try:
            txt = (await node.inner_text()).strip()
        except Exception:
            continue
        if txt:
            answers.append({'index': idx + 1, 'text': txt[:4000]})
    return answers


async def read_with_playwright(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = await browser.new_context(
            viewport={'width': 1440, 'height': 900},
            user_agent=DEFAULT_UA,
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            await page.wait_for_timeout(3000)
            title = await page.title()
            html = await page.content()
            return title, html, page
        finally:
            await browser.close()


async def read_page(url: str):
    page_type = classify_url(url)
    title = ''
    html = ''
    playwright_ok = True

    try:
        title, html, _ = await read_with_playwright(url)
    except Exception as e:
        playwright_ok = False
        title = f'Playwright unavailable: {e.__class__.__name__}'

    if not playwright_ok:
        try:
            headers = {'User-Agent': DEFAULT_UA, 'Referer': 'https://www.zhihu.com/'}
            r = requests.get(url, headers=headers, timeout=20)
            title = title or f'HTTP {r.status_code}'
            html = r.text
        except Exception as e:
            return {'url': url, 'type': page_type, 'error': str(e)}

    if page_type == 'question':
        q_sel, q_txt = extract_text_from_html(html, QUESTION_SELECTORS)
        result = {
            'url': url,
            'type': page_type,
            'title': title,
            'question_selector': q_sel,
            'question_text': q_txt,
            'html_preview': html[:5000],
        }
        if playwright_ok:
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
                    context = await browser.new_context(
                        viewport={'width': 1440, 'height': 900},
                        user_agent=DEFAULT_UA,
                        locale='zh-CN',
                        timezone_id='Asia/Shanghai',
                    )
                    page = await context.new_page()
                    await page.goto(url, wait_until='domcontentloaded', timeout=45000)
                    await page.wait_for_timeout(3000)
                    answers = await collect_answers(page)
                    result['answers_count'] = len(answers)
                    result['answers'] = answers
                    await browser.close()
            except Exception:
                pass
        return result

    if page_type == 'answer':
        a_sel, a_txt = extract_text_from_html(html, ANSWER_SELECTORS)
        return {
            'url': url,
            'type': page_type,
            'title': title,
            'answer_selector': a_sel,
            'answer_text': a_txt,
            'html_preview': html[:5000],
        }

    if page_type == 'article':
        a_sel, a_txt = extract_text_from_html(html, ARTICLE_SELECTORS)
        return {
            'url': url,
            'type': page_type,
            'title': title,
            'article_selector': a_sel,
            'article_text': a_txt,
            'html_preview': html[:5000],
        }

    return {
        'url': url,
        'type': page_type,
        'title': title,
        'visible_text': html[:8000],
        'html_preview': html[:5000],
    }


async def main():
    if len(sys.argv) < 2:
        print('Usage: zhihu_reader.py <url>')
        sys.exit(1)
    url = sys.argv[1]
    result = await read_page(url)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
