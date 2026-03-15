"""
Extract and run cells 1-9 from the notebook to verify correctness.
"""
import json, sys, os
os.chdir("/home/user/mc_retirement")

with open("mc_retirement.ipynb") as f:
    nb = json.load(f)

cells = nb["cells"]

# Build combined source, collecting cells 1-9 (code only)
combined_lines = []
for i in range(10):
    c = cells[i]
    if c["cell_type"] == "code":
        src = "".join(c["source"])
        combined_lines.append(f"\n# ===== CELL {i} =====\n")
        combined_lines.append(src)

full_code = "\n".join(combined_lines)

# Sanitize the trailing `params` display expression that would cause issues in exec
# (bare expression at end of cell 6)
full_code = full_code.rstrip()

# Write to a .py file then exec it
with open("/tmp/mc_run_cells.py", "w") as f:
    f.write(full_code)

print("Running notebook cells 0-9...")
import subprocess
result = subprocess.run(["python3", "/tmp/mc_run_cells.py"],
                       capture_output=True, text=True, cwd="/home/user/mc_retirement")
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[-3000:])
print("Return code:", result.returncode)
