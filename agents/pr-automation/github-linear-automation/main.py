"""
github-linear-automation
Run: python main.py --target qa|prod
Queries Linear, scans repos, cherry-picks commits, opens PRs.
"""

import argparse
import logging
import os
import sys

# Ensure logs/ exists before any logging setup
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/automation.log"),
    ],
)

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cherry-pick Linear tickets to GitHub release branches.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --target qa      # Create QA release PRs
  python main.py --target prod    # Create Prod release PRs
  python main.py                  # Interactive prompt for target
        """,
    )
    parser.add_argument(
        "--target", "-t",
        choices=["qa", "prod"],
        help="Release target: 'qa' (→ qa branch) or 'prod' (→ main branch)",
    )
    parser.add_argument(
        "--resolve-conflicts",
        action="store_true",
        help="Attempt to auto-resolve conflicts using Claude CLI",
    )
    args = parser.parse_args()

    # If no target specified, prompt interactively
    target = args.target
    if not target:
        print("\n🍒 Cherry — GitHub-Linear Release Automation\n")
        print("Which release do you want to create?")
        print("  [1] QA Release   → cherry-pick to 'qa' branch")
        print("  [2] Prod Release → cherry-pick to 'main' branch")
        print()
        
        while True:
            choice = input("Enter 1 or 2 (or 'qa'/'prod'): ").strip().lower()
            if choice in ("1", "qa"):
                target = "qa"
                break
            elif choice in ("2", "prod"):
                target = "prod"
                break
            else:
                print("Invalid choice. Please enter 1, 2, 'qa', or 'prod'.")

    from core.release_manager import ReleaseManager

    manager = ReleaseManager(release_target=target)
    prs = manager.run_release(resolve_conflicts=args.resolve_conflicts)

    if prs:
        print(f"\n✅  Done — {len(prs)} PR(s) created:")
        for repo, pr in prs.items():
            print(f"   {repo}: {pr.url}")
    else:
        print("\nℹ️  No PRs created — check logs/automation.log for details.")


if __name__ == "__main__":
    main()
