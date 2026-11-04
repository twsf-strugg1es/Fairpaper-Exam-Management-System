# Load test (task 5.2)

Simulates exam day. 500 candidates sign in and start one exam within a minute, then write for ten minutes the way the exam page does:
- an answer saved every 10 to 30 seconds;
- the clock checked once a minute;
- now and then a focus change reported.

When the test stops, everyone submits.

The targets come from `docs/02-TRD.md` ("Performance and reliability targets"):

| Request | Target |
|---|---|
| Start the exam | p95 < 1.5 s, with 500 candidates starting within 60 s |
| Save an answer | p95 < 500 ms at 500 concurrent candidates |

The run exits with code 1 when either target is missed or any request fails.

## Before you run it

Run it against a staging environment sized like production (task 6.1), never against production. Set these on the API:

- `RATE_LIMITS=off`. All the traffic comes from one machine, so the per-IP sign-in and signup limits would stop it.
- `EMAIL_BACKEND=console`. Each seeded candidate signs up, which sends a confirmation email to an `@example.com` address.

## Run it

```bash
pip install -r loadtest/requirements.txt
python loadtest/seed.py --api https://staging-api.example.com --candidates 500
locust -f loadtest/locustfile.py --host https://staging-api.example.com --headless -u 500 -r 9 -t 10m --csv loadtest/results
```

`-r 9` starts 9 candidates a second, so all 500 have started within a minute. Seed again before every run: a candidate can start the exam only once, and the test submits at the end.

When the run ends, it prints the p95 for both targets. It also writes `loadtest/results_stats.csv`, with every request's percentiles, and `loadtest/results_stats_history.csv`, with the same numbers over time. Record the results, and the size of the infrastructure, in the TRD's performance table.

## What to tune when a target is missed

- **API processes.** The Docker image runs one uvicorn process. Sign-ins hash a password, which is CPU-heavy, so a burst of sign-ins queues behind that one process. More processes or more containers fix it. Rate limits and background jobs then need to be shared across processes (Redis or the database; see the TRD).
- **Database connections.** SQLAlchemy keeps 5 connections per process and opens up to 10 more. Starting an exam runs 17 statements and saving an answer 9. Neither grows with the number of questions or exams, and `backend/tests/test_query_counts.py` keeps it that way. Set `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` on the API to change the pool.
- **The database itself:** its size, and whether it's close to the API.
