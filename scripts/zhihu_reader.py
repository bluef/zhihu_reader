#!/usr/bin/env python3
"""
Unified Zhihu page reader.

Capabilities:
- question page
- answer page
- article page
- keyword search helper
- optional cookie support via ZHIHU_COOKIE
- optional request headers support via ZHIHU_HEADERS_JSON
- Zhihu questions answers API extraction when available
- fallback to HTML/debug saving when content extraction fails
- fallback to requests when Playwright browser is unavailable
"""
import argparse
import asyncio
import html as htmlmod
import json
import os
import re
import sys
from urllib.parse import quote

import requests
from playwright.async_api import async_playwright

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


def parse_cookie_string(cookie_string: str):
    cookies = {}
    for item in cookie_string.split(';'):
        item = item.strip()
        if not item or '=' not in item:
            continue
        k, v = item.split('=', 1)
        cookies[k.strip()] = v.strip()
    return cookies


def parse_json_env(name: str):
    raw = os.getenv(name, '').strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def build_headers(extra=None, referer='https://www.zhihu.com/'):
    headers = {
        'User-Agent': DEFAULT_UA,
        'Referer': referer,
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
    }
    if extra and isinstance(extra, dict):
        for k, v in extra.items():
            if v is None:
                continue
            headers[str(k)] = str(v)
    return headers


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


async def read_with_playwright(url: str, extra_headers=None):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = await browser.new_context(
            viewport={'width': 1440, 'height': 900},
            user_agent=DEFAULT_UA,
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            extra_http_headers=build_headers(extra_headers, referer=url),
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


async def read_with_requests(url: str, cookies=None, extra_headers=None):
    session = requests.Session()
    session.headers.update(build_headers(extra_headers, referer=url))
    if cookies:
        session.cookies.update(cookies)
    r = session.get(url, timeout=20)
    return f'HTTP {r.status_code}', r.text, r


def extract_question_id(url: str):
    m = re.search(r'/question/(\d+)', url)
    return m.group(1) if m else None


def fetch_question_answers_api(url: str, cookies=None, extra_headers=None, limit=20):
    qid = extract_question_id(url)
    if not qid:
        return None
    session = requests.Session()
    session.headers.update(build_headers(extra_headers, referer=url))
    if cookies:
        session.cookies.update(cookies)
    api = f'https://www.zhihu.com/api/v4/questions/{qid}/answers'
    params = {
        'limit': limit,
        'offset': 0,
        'sort_by': 'default',
        'include': 'data[*].author,content,voteup_count,comment_count,created_time,updated_time,excerpt,question,excerpt_length,is_normal,is_sticky,is_collapsed,admin_closed_comment,relationship.is_authorized',
    }
    r = session.get(api, params=params, timeout=20)
    if r.status_code != 200:
        return {'status_code': r.status_code, 'error': r.text[:500]}
    try:
        data = r.json()
    except Exception as e:
        return {'error': str(e)}
    results = []
    for item in data.get('data', []):
        author = item.get('author') or {}
        excerpt = item.get('excerpt') or ''
        content = item.get('content') or ''
        content = htmlmod.unescape(re.sub(r'<[^>]+>', ' ', content))
        content = ' '.join(content.split())
        results.append({
            'author': author.get('name'),
            'headline': author.get('headline', ''),
            'voteup_count': item.get('voteup_count', 0),
            'comment_count': item.get('comment_count', 0),
            'excerpt': excerpt,
            'content': content[:1600],
        })
    return results


def search_candidates(keyword: str):
    q = quote(f'site:zhihu.com {keyword}')
    return {
        'keyword': keyword,
        'hint_url': f'https://www.zhihu.com/search?type=content&q={q}',
        'note': 'Zhihu search may require login or be blocked. If search is inaccessible, provide a question URL or title.'
    }


async def read_page(url: str):
    page_type = classify_url(url)
    title = ''
    html = ''
    playwright_ok = True
    cookies = None
    cookie_string = os.getenv('ZHIHU_COOKIE', '').strip()
    if cookie_string:
        cookies = parse_cookie_string(cookie_string)
    extra_headers = parse_json_env('ZHIHU_HEADERS_JSON')

    try:
        title, html, _ = await read_with_playwright(url, extra_headers=extra_headers)
    except Exception as e:
        playwright_ok = False
        title = f'Playwright unavailable: {e.__class__.__name__}'

    if not html:
        try:
            title, html, _ = await read_with_requests(url, cookies=cookies, extra_headers=extra_headers)
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

        api_answers = fetch_question_answers_api(url, cookies=cookies, extra_headers=extra_headers, limit=20)
        if isinstance(api_answers, list):
            result['answers_count'] = len(api_answers)
            result['answers'] = api_answers
        elif isinstance(api_answers, dict) and api_answers.get('error'):
            result['answers_api_error'] = api_answers

        if playwright_ok and 'answers' not in result:
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
                    context = await browser.new_context(
                        viewport={'width': 1440, 'height': 900},
                        user_agent=DEFAULT_UA,
                        locale='zh-CN',
                        timezone_id='Asia/Shanghai',
                        extra_http_headers=build_headers(extra_headers, referer=url),
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
    parser = argparse.ArgumentParser()
    parser.add_argument('target', help='Zhihu URL or search keyword')
    parser.add_argument('--search', action='store_true', help='Treat target as a keyword and return candidate Zhihu search info')
    args = parser.parse_args()

    if args.search or not (args.target.startswith('http://') or args.target.startswith('https://')):
        print(json.dumps(search_candidates(args.target), ensure_ascii=False, indent=2))
        return

    result = await read_page(args.target)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
