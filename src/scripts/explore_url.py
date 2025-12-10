# scripts/explore_url.py
import json
import sys
from pathlib import Path
from agent.pipelines.exploration_pipeline import ExplorationPipeline
from dataclasses import asdict

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/explore_url.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    pipeline = ExplorationPipeline(use_llm_summary=True)
    snapshot = pipeline.run(url)

    out_dir = Path("artifacts/snapshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_name = snapshot.url.replace("://", "_").replace("/", "_")
    out_path = out_dir / f"{safe_name}.json"

    data = asdict(snapshot)
    # convert ElementDescriptor list to pure dict list (asdict already handles nested dataclasses)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    print(f"[OK] Snapshot saved to {out_path}")

if __name__ == "__main__":
    main()
