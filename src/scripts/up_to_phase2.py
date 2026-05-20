from pathlib import Path
import json
from agent.pipelines.exploration_pipeline import ExplorationPipeline
from agent.pipelines.test_design_pipeline import TestDesignPipeline
from agent.visualization.coverage_overlay import create_coverage_overlay

# 1) Phase 1 – snapshot
explorer = ExplorationPipeline(use_llm_summary=True)
snapshot = explorer.run("https://www.youtube.com/")

# 2) Phase 2 – initial test plan
designer = TestDesignPipeline()
plan = designer.propose_plan(snapshot, human_feedback=None)

# 3) Save plan
out = Path("artifacts/test_plans/youtube.com_plan.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")

# 4) Generate coverage overlay image
overlay_path = create_coverage_overlay(plan)
print("Coverage overlay at:", overlay_path)
