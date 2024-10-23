from dataset import Dataset
import os
from pathlib import Path

project_dir = Path(__file__).parent.parent.as_posix()

def main():
    dataset = Dataset("experiment/domains/gpt-4o")

    for time_step in dataset:
        if time_step["type"] != "goal":
            continue
        print("Planning for time step", time_step["time"])
        problem_file = time_step['problem_path']
        plan_file = os.path.join(Path(problem_file).parent, "true_plan.pddl")
        os.system(f"sudo docker run --rm -v {project_dir}:/root/experiments lapkt/lapkt-public ./siw-then-bfsf " + \
            f"--domain /root/experiments/{dataset.domain_path} " + \
            f"--problem /root/experiments/{time_step['problem_path']} " + \
            f"--output /root/experiments/{plan_file} " + \
            f"> /dev/null")
        
    print("Finished planning")

if __name__ == "__main__":
    main()