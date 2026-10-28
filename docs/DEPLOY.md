# Deploying Ask Your Data publicly (free tiers)

```
Visitor's browser ──► Vercel (Next.js frontend) ──► Render (FastAPI backend) ──► Neon (PostgreSQL)
                                                            │
                                                            └──► OpenAI API
```

| Part | Service | Free plan notes |
|---|---|---|
| Database | Neon | 1 GB storage per project (our table is ~340 MB). Sleeps after 5 min idle, wakes in about a second |
| Backend | Render | Sleeps after 15 min idle; first request after that takes about a minute. 750 free hours a month |
| Frontend | Vercel | Hobby plan, always on |
| LLM | OpenAI | Paid per use. **Set a monthly budget limit in the OpenAI dashboard before going public** |

Region: use **Singapore** for both Neon and Render (closest to India, and keeps backend↔database fast).

---

## Step 0: Protect your OpenAI credit (5 min)

1. platform.openai.com → **Settings → Limits** (or Billing → Usage limits): set a monthly budget, e.g. $5.
2. The backend also limits questions: 6 per minute and 20 per day per visitor, and 300 per day for everyone combined (set in `render.yaml`; counters reset when the server restarts, so the OpenAI budget is the real safety net).
3. Optional: create a separate OpenAI API key just for the demo, so you can revoke it without affecting anything else.

## Step 1: Push the code to GitHub

Render and Vercel deploy from GitHub.

```powershell
cd C:\Projects\ask-your-data
git init
git add .
git status            # .env must NOT be listed
git commit -m "Ask Your Data"
git branch -M main
git remote add origin https://github.com/<you>/ask-your-data.git
git push -u origin main
```

## Step 2: Database on Neon (10 min)

1. Sign up at **neon.com** → **Create project**: name `ask-your-data`, Postgres version 17, region **AWS Asia Pacific (Singapore)**.
2. On the project dashboard click **Connect** and copy the connection string. It looks like:
   `postgresql://neondb_owner:XXXX@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
3. Copy your local data into Neon. Docker Desktop must be running and `ayd-postgres` up. Paste your Neon string between the quotes (one line):

```powershell
docker exec ayd-postgres bash -c "pg_dump -U postgres -d bankdb --no-owner --no-privileges -t loan_portfolio | psql 'PASTE_NEON_CONNECTION_STRING_HERE'"
```

   Takes 1–3 minutes. Check it:

```powershell
docker exec ayd-postgres psql "PASTE_NEON_CONNECTION_STRING_HERE" -c "SELECT COUNT(*) FROM loan_portfolio;"
```
   Must say **1000000**.

4. Create the read-only user. Open `db\neon_readonly_role.sql`, replace `CHANGE_ME` with a long random password (letters and numbers only, 20+ characters), save, then:

```powershell
Get-Content db\neon_readonly_role.sql | docker exec -i ayd-postgres psql "PASTE_NEON_CONNECTION_STRING_HERE"
```

5. Build the app's connection string: take your Neon string and replace `neondb_owner:XXXX` with `nl2sql_reader:YOUR_PASSWORD`:
   `postgresql://nl2sql_reader:YOUR_PASSWORD@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
   This is your **DATABASE_URL** for Render. The owner string stays private and is never given to the app.

## Step 3: Backend on Render (10 min)

1. Sign up at **render.com** with GitHub.
2. **New + → Blueprint** → select the `ask-your-data` repo. Render reads `render.yaml`.
3. Fill in the three secret values when asked:
   - `DATABASE_URL`: the read-only string from step 2.5
   - `OPENAI_API_KEY`: your key
   - `CORS_ORIGINS`: put `https://example.com` for now; you'll fix it after step 4
4. **Apply**. The first build takes about 5 minutes.
5. Copy the service URL, e.g. `https://ask-your-data-api.onrender.com`, and open `<URL>/api/health`. You want `"database": true`.

## Step 4: Frontend on Vercel (5 min)

1. Sign up at **vercel.com** with GitHub → **Add New → Project** → import `ask-your-data`.
2. **Root Directory**: click Edit and choose `frontend`. Framework is detected as Next.js.
3. **Environment Variables**: `NEXT_PUBLIC_API_URL` = your Render URL (no trailing slash).
4. **Deploy**. You get a URL like `https://ask-your-data.vercel.app`.

## Step 5: Connect them (2 min)

1. Render → your service → **Environment** → set `CORS_ORIGINS` to your exact Vercel URL (no trailing slash) → Save. Render redeploys.
2. Open your Vercel URL. The first load may show "Starting the demo server…" for up to a minute. Then ask a question.

## Optional: avoid the 1-minute wake-up

Free Render services sleep after 15 minutes without traffic. A free uptime monitor (e.g. UptimeRobot or cron-job.org) calling `<Render URL>/api/health` every 10 minutes keeps it awake. One service running all month uses about 744 of the 750 free hours. Neon will still sleep after 5 minutes, but it wakes in about a second.

## Updating later

Push to GitHub. Render and Vercel both redeploy automatically from `main`.

## Troubleshooting

| Problem | Fix |
|---|---|
| Frontend says it can't reach the API | `NEXT_PUBLIC_API_URL` wrong (redeploy Vercel after changing it), or `CORS_ORIGINS` doesn't exactly match the Vercel URL |
| `/api/health` shows `"database": false` | Wrong `DATABASE_URL`; it must end with `?sslmode=require` |
| Render build fails on Python version | `backend/.python-version` must say `3.12` |
| "The language model is not configured" | `OPENAI_API_KEY` missing or wrong on Render |
| Answers suddenly fail after a while | OpenAI budget limit reached; check the OpenAI dashboard |
