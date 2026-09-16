# GitHub -> Vast execution workflow

Canonical code-transfer repository:

- SSH: `git@github.com:tungooxx/Plancarry.git`
- HTTPS: `https://github.com/tungooxx/Plancarry`

## Local/GPU-lab

Work in `/workspace/local-vlm/LLM/plancarry`, commit reproducible source/design changes, and push to `main`.
Do not commit `.env`, SSH/private keys, Hugging Face/model caches, virtual environments, or generated sealed scientific outputs.

## Vast

Clone once:

```bash
git clone git@github.com:tungooxx/Plancarry.git
cd Plancarry
```

For later runs:

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
git rev-parse HEAD
```

Before any scientific execution, record/verify the exact Git commit SHA and the declared model/runtime environment against the Research OS Experiment/ResearchDecision. Moving execution to Vast is a technical host change only; it does not authorize changes to frozen populations, seeds, model revision, precision, hook sites, intervention rules, metrics, gates, or sealed-result handling.

Run exact-runtime canaries/equivalence checks whenever required by the frozen experiment contract before interpreting outcomes.
