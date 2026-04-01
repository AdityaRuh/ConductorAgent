import logging
import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


class GitHubClient:
    def __init__(self, pat: str):
        self._http = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "Authorization": f"Bearer {pat}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def fetch_pr_diff(self, owner: str, repo: str, pr_number: int) -> str:
        """Fetch PR diff by getting file patches from the files endpoint."""
        resp = await self._http.get(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
            params={"per_page": 100},
        )
        resp.raise_for_status()
        files = resp.json()
        return self._build_diff_from_files(files)

    async def fetch_compare_diff(self, owner: str, repo: str, base_sha: str, head_sha: str) -> str:
        """Fetch compare diff using the compare endpoint files."""
        resp = await self._http.get(
            f"/repos/{owner}/{repo}/compare/{base_sha}...{head_sha}",
        )
        resp.raise_for_status()
        data = resp.json()
        return self._build_diff_from_files(data.get("files", []))

    @staticmethod
    def _build_diff_from_files(files: list[dict]) -> str:
        """Convert GitHub PR files response into unified diff format."""
        diff_parts = []
        for f in files:
            patch = f.get("patch")
            if not patch:
                continue
            filename = f["filename"]
            prev = f.get("previous_filename", filename)
            status = f.get("status", "modified")
            if status == "added":
                a_path = "/dev/null"
                b_path = "b/" + filename
                header = "diff --git a/{fn} b/{fn}\nnew file mode 100644\n--- {a}\n+++ {b}".format(
                    fn=filename, a=a_path, b=b_path
                )
            elif status == "removed":
                a_path = "a/" + prev
                b_path = "/dev/null"
                header = "diff --git a/{p} b/{p}\ndeleted file mode 100644\n--- {a}\n+++ {b}".format(
                    p=prev, a=a_path, b=b_path
                )
            elif status == "renamed":
                header = "diff --git a/{p} b/{fn}\nrename from {p}\nrename to {fn}\n--- a/{p}\n+++ b/{fn}".format(
                    p=prev, fn=filename
                )
            else:
                header = "diff --git a/{fn} b/{fn}\n--- a/{fn}\n+++ b/{fn}".format(fn=filename)
            diff_parts.append(header + "\n" + patch)
        return "\n".join(diff_parts)

    async def fetch_context_md(self, owner: str, repo: str, ref: str) -> str | None:
        try:
            resp = await self._http.get(
                f"/repos/{owner}/{repo}/contents/CONTEXT.md",
                params={"ref": ref},
            )
            resp.raise_for_status()
            data = resp.json()
            import base64
            return base64.b64decode(data["content"]).decode("utf-8")
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404):
                logger.info("No CONTEXT.md found in %s/%s (ref=%s) [%d]", owner, repo, ref, e.response.status_code)
                return None
            raise

    async def fetch_user_email(self, username: str) -> str | None:
        """Fetch a GitHub user's public email via the Users API."""
        try:
            resp = await self._http.get(f"/users/{username}")
            resp.raise_for_status()
            return resp.json().get("email")
        except httpx.HTTPStatusError:
            logger.warning("Could not fetch GitHub user profile for %s", username)
            return None

    async def fetch_pr_info(self, owner: str, repo: str, pr_number: int) -> dict:
        resp = await self._http.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
        resp.raise_for_status()
        return resp.json()

    async def post_review(self, owner: str, repo: str, pr_number: int, commit_sha: str, body: str, comments: list[dict]) -> None:
        payload = {"commit_id": commit_sha, "body": body, "event": "COMMENT", "comments": comments}
        resp = await self._http.post(f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews", json=payload)
        resp.raise_for_status()
        logger.info("Posted review on %s/%s#%d", owner, repo, pr_number)

    async def post_comment(self, owner: str, repo: str, pr_number: int, body: str) -> None:
        resp = await self._http.post(f"/repos/{owner}/{repo}/issues/{pr_number}/comments", json={"body": body})
        resp.raise_for_status()

    async def close(self):
        await self._http.aclose()
