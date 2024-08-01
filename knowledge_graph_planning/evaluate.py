from sim import Result
import os
import matplotlib.pyplot as plt
import numpy as np

total_update_success = np.zeros(100)
total_goal_success = np.zeros(20)

for i in range(1, 2):
    run_dir = f"experiments/experiment3/runs/run{i}"
    with open(os.path.join(run_dir, "report.txt"), "r") as f:
        lines = f.read().splitlines()
    results = [Result.from_str(line) for line in lines]
    results.sort(key=lambda x: x.time)

    update_times = []
    update_success_count = 0
    update_count = 0

    goal_times = []
    goal_success_count = 0
    goal_count = 0

    for result in results:
        if result.time_step_type == "state_change":
            update_count += 1
            update_success_count += result.success
            total_update_success[update_count - 1] += update_success_count / update_count
            update_times.append(result.time)
        elif result.result_type == "state":
            goal_count += 1
            goal_success_count += result.success
            total_goal_success[goal_count - 1] += goal_success_count / goal_count
            goal_times.append(result.time)


plt.style.use("seaborn-v0_8-ticks")
plt.plot(update_times, total_update_success / 1, label="Running Percent State Change Success")
plt.plot(goal_times, total_goal_success / 1, label="Running Percent Goal Success")
plt.xlabel("Time")
plt.legend()
plt.show()