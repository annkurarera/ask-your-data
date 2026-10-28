# LinkedIn post draft (Day 1 of 7)

Fill in the numbers from your `eval/results/*.md` report before posting. Attach a 60–90 second screen recording.

---

Day 1/7 of building 7 AI apps in 7 days 🚀

I built "Ask Your Data": ask a bank's loan portfolio a question in plain English, and get the answer, a chart and the SQL behind it.

"Which 10 branches have the highest NPA %?" → answered in [X] seconds, on 10 lakh loans.

What's under the hood:
→ A semantic layer that teaches the LLM what Gross NPA %, AUM, FOIR and the Indian financial year mean
→ Self-correction: if the SQL fails, the error goes back to the model and it fixes its own query
→ 3 layers of safety: a SQL validator, a read-only database role, and read-only transactions with a timeout

How I tested it:
✅ [XX]% execution accuracy on a 30-question golden set (easy / medium / hard: [x]/10, [x]/12, [x]/8)
✅ [15/15] adversarial prompts blocked: DROP TABLE, prompt injection, system tables, pg_sleep
✅ 91 backend tests + 18 frontend tests in CI
✅ ~$[0.00X] per question

The biggest lesson: accuracy went from [X]% to [Y]% without changing the model, just by improving the semantic layer. The business definitions matter more than the LLM.

Stack: Python, FastAPI, PostgreSQL, LiteLLM, sqlglot, Next.js, Playwright

GitHub: [link]
Live demo: [link]

Tomorrow: Day 2 — [next project].

#DataScience #AIEngineering #TextToSQL #LLM #BFSI
