# AI Intake Live Provider Evaluation

Live DeepSeek evaluation is off by default. All gates must pass: synthetic dataset, non-production environment, `AI_INTAKE_LIVE_EVAL_ENABLED=true`, explicit `--allow-live-provider`, configured key/model, positive bounded case count, and configured output/input caps.

Example for authorized isolated staging only:

```bash
python manage.py evaluate_ai_intake --provider deepseek --allow-live-provider --max-cases 3
```

Command refuses Railway/production markers. Never use real patient text. Never log request/response bodies or credentials. Live results need human review; no deployment or clinical-validity claim follows from a passing run.
