import os, httpx

tok = os.environ["REFRESH_GITHUB_TOKEN"].strip()
repo, wf = "Ayan-Ahmad-0/insight", "refresh-marts.yml"
h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
     "X-GitHub-Api-Version": "2022-11-28"}
base = f"https://api.github.com/repos/{repo}/actions/workflows/{wf}"

r = httpx.get(base, headers=h)
print("1. find the workflow:", r.status_code, r.json().get("message") or r.json().get("state"))

r = httpx.post(base + "/dispatches", headers=h,
               json={"ref": "main", "inputs": {"requested_by": "manual-test"}})
print("2. start it:", r.status_code, r.text[:300] or "(empty body means success)")