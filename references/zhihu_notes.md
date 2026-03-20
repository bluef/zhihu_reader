# Zhihu Notes

## Fallback order
1. requests / direct HTML
2. Playwright render
3. login or cookie retry
4. HTML/body text fallback
5. Explicitly report partial visibility

## Common failure modes
- 403 / security notice
- login wall
- validation page
- dynamic loading hides answers from initial HTML
- only partial answers available

## Selectors
### Question page
- `.Question-main`
- `.QuestionHeader`
- `.QuestionHeader-content`

### Answer page
- `.AnswerItem`
- `.Answer`
- `.ContentItem-answer`
- `.RichContent-inner`

### Article page
- `.Post-RichTextContainer`
- `.RichText`
- `.ztext`
- `article`
- `.Post-content`

## Output
When researching a Zhihu question, return:
- title
- visible answer count
- answer author / upvotes / excerpt when available
- themes and disagreements
- what cannot be accessed
