import sys
import os

# Add src to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src_root = os.path.join(project_root, "src")
if src_root not in sys.path:
    sys.path.append(src_root)

from generators.code_generator import CodeGenerator
from loguru import logger

def main():
    test_plan_path = os.path.join(project_root, "src", "artifacts", "test_plans", "test_plan.json")
    output_dir = os.path.join(project_root, "artifacts", "generated_tests")
    print(test_plan_path)
    if not os.path.exists(test_plan_path):
        logger.error(f"Test plan not found at {test_plan_path}")
        return

    logger.info(f"Generating tests from {test_plan_path} to {output_dir}")
    
    generator = CodeGenerator(test_plan_path, output_dir)
    generator.generate()
    
    logger.info("Done!")

if __name__ == "__main__":
    main()
