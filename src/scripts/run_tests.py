import os
import subprocess
import sys

def run_tests():
    # Get the directory where this script is located (src/scripts)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Go up two levels to get to the project root
    project_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    
    # Define the target directory where the generated code lives
    generated_tests_dir = os.path.join(project_root, "artifacts", "generated_tests")
    
    # Check if the directory exists
    if not os.path.exists(generated_tests_dir):
        print(f"❌ Error: Generated tests directory not found at: {generated_tests_dir}")
        print("Make sure you have run the generator first.")
        return

    print(f"📂 Changing working directory to: {generated_tests_dir}")
    
    # Change the current working directory
    # This fixes the "ModuleNotFoundError" or "Failed to canonicalize" errors
    os.chdir(generated_tests_dir)

    # Construct the pytest command
    # We use sys.executable to ensure we use the same python interpreter (virtual env)
    command = [sys.executable, "-m", "pytest", "tests"]
    
    # Pass through any extra arguments (like --headed or --slowmo 1000)
    command.extend(sys.argv[1:])

    print(f"🚀 Running command: {' '.join(command)}")
    print("-" * 60)

    # Run the command
    try:
        result = subprocess.run(command)
        print("-" * 60)
        if result.returncode == 0:
            print("✅ All tests passed successfully!")
        else:
            print("❌ Tests failed.")
            sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n⚠️ Test execution interrupted.")

if __name__ == "__main__":
    run_tests()