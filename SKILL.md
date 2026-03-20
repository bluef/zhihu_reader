---
name: zhihu-page-reader
description: 读取和研究知乎问题页、回答页和专栏文章页；当用户提供知乎链接，或要求提取正文、答案、作者、赞同数、摘要，或研究某个知乎问题的答案分布时使用。也支持按关键词返回知乎候选搜索入口，并可通过 ZHIHU_COOKIE / ZHIHU_HEADERS_JSON 注入请求态。
---

# Zhihu Page Reader

读取知乎网页并做结构化研究。

## 何时使用

- 用户给出知乎链接
- 用户要求研究某个知乎问题的答案
- 用户要求提取知乎正文、摘要、作者、赞同数、评论或可见答案
- 用户只给关键词，希望先找知乎候选问题

## 工作顺序

1. 先用 `requests` 读公开 HTML
2. 再用 Playwright 渲染页面
3. 如已配置 `ZHIHU_COOKIE`，优先用它重试 question answers API
4. 如已配置 `ZHIHU_HEADERS_JSON`，用于补充请求头
5. 若被反爬或登录限制，明确说明只拿到部分内容

## 输出要求

尽量给出：
- 标题
- 可见答案数
- 每条答案的作者、赞同数、摘要
- 主题归类与结论
- 拿不到内容的原因

## 使用脚本

- `scripts/zhihu_reader.py`：统一入口，支持问题页 / 回答页 / 文章页 / 关键词搜索提示

## 参考

- `references/zhihu_notes.md`：常见失败模式、选择器、输出要求
