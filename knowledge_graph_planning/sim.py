from __future__ import annotations
import sys
from typing import IO
from contextlib import redirect_stdout
import os
from pathlib import Path
from difflib import ndiff

from dataset.dataset import Dataset

from knowledge_graph_planning.knowledge_graph.age import AgeGraphStore
from knowledge_representation.knowledge_loader import load_knowledge_from_yaml, populate_with_knowledge # type: ignore
from knowledge_representation._libknowledge_rep_wrapper_cpp import LongTermMemoryConduit # type: ignore

from knowledge_graph.load_graph import load_graph
from knowledge_graph.agent import KGBaseAgent, KGAgent
from knowledge_graph.utils import reset_database

# set API key
openai_keys_file = os.path.join(os.getcwd(), "keys/openai_keys.txt")
with open(openai_keys_file, "r") as f:
	keys = f.read()
keys = keys.strip().split('\n')
os.environ["OPENAI_API_KEY"] = keys[0]

project_dir = Path(__file__).parent.parent.as_posix()

class KGSim:
	def __init__(self, dataset: Dataset, agent: KGBaseAgent, log_dir: str) -> None:
		self.dataset = dataset
		self.agent = agent
		self.log_dir = log_dir
	
	def run(self):
		# configure_db_script = os.path.join(os.path.dirname(__file__), "knowledge_graph/configure_postgresql.sh")
		# os.system(f"{configure_db_script} -S password knowledge_base_truth")
		reset_database(
			dbname="knowledge_base_truth",
			user=self.agent.dbuser,
			password=self.agent.dbpass,
			host=self.agent.dbhost,
			port=self.agent.dbport,
			schema_file=self.agent.dbschema
		)
		all_knowledge = [load_knowledge_from_yaml(self.dataset.initial_knowledge_path)]
		populate_with_knowledge(LongTermMemoryConduit("knowledge_base_truth", "localhost"), all_knowledge)
		load_graph("knowledge_base_truth", "knowledge_graph")
		truth_graph_store = AgeGraphStore(
			"knowledge_base_truth",
			"postgres",
			"password",
			"localhost",
			5432,
			"knowledge_graph",
			"entity",
		) # type: ignore

		report: list[Result] = []
		previous_diff = []
		print(f"Initial State:\n{self.dataset.initial_state}")
		self.agent.input_initial_state(self.dataset.initial_state, self.dataset.initial_knowledge_path, self.dataset.predicate_names, self.dataset.domain_path)
		for time_step in self.dataset:
			if time_step["type"] == "state_change":
				print("\nTime: " + str(time_step["time"]))
				print(f"State change: {time_step['state_change']}")
				self.agent.input_state_change(time_step["state_change"])
				print("Completed state change")
			elif time_step["type"] == "goal":
				print("\nTime: " + str(time_step["time"]))
				print(f"Goal: {time_step['goal']}")
				predicted_plan = self.agent.answer_planning_query(time_step["goal"], truth_graph_store)
				print("Generated plan")

				if "true_plan_pddl" in time_step:
					true_plan = time_step["true_plan_pddl"].splitlines()
				else:
					plan_file = "true_plan.pddl"
					os.system(f"sudo docker run --rm -v {project_dir}:/root/experiments lapkt/lapkt-public ./siw-then-bfsf " + \
						f"--domain /root/experiments/{self.dataset.domain_path} " + \
						f"--problem /root/experiments/{time_step['problem_path']} " + \
						f"--output /root/experiments/{plan_file} " + \
						f"> /dev/null")
					with open(os.path.join(project_dir, plan_file), "r") as f:
						true_plan = f.read().splitlines()
					os.remove(os.path.join(project_dir, plan_file))
				
				if true_plan != predicted_plan:
					print("Conflicting expected plan and predicted plan")
					report.append(Result(time_step["time"], "plan", time_step["type"], False))
					with open(os.path.join(self.log_dir, f"{time_step['time']:04d}_plan.diff"), "w") as f:
						f.write("\n".join(ndiff(true_plan, predicted_plan)))
				else:
					print("Plan is correct")
					report.append(Result(time_step["time"], "plan", time_step["type"], True))
			else:
				continue

			truth_graph_store._conn.close()
			# os.system('sudo -u postgres psql -c "drop database knowledge_base_truth"')

			# os.system(f"{configure_db_script} password knowledge_base_truth >/dev/null 2>&1")
			reset_database(
				dbname="knowledge_base_truth",
				user=self.agent.dbuser,
				password=self.agent.dbpass,
				host=self.agent.dbhost,
				port=self.agent.dbport,
				schema_file=self.agent.dbschema
			)
			all_knowledge = [load_knowledge_from_yaml(time_step["knowledge_path"])]
			populate_with_knowledge(LongTermMemoryConduit("knowledge_base_truth", "localhost"), all_knowledge)
			load_graph("knowledge_base_truth", "knowledge_graph")
			truth_graph_store = AgeGraphStore(
				"knowledge_base_truth",
				"postgres",
				"password",
				"localhost",
				5432,
				"knowledge_graph",
				"entity",
			) # type: ignore

			triplets_truth = truth_graph_store.query("MATCH (V)-[R]->(V2) RETURN V.name, type(R), V2.name", return_count=3)
			triplets_truth = [" -> ".join(item[1:-1] for item in row) for row in triplets_truth if all(isinstance(s, str) for s in row)]
			triplets_truth.sort()
			triplets_pred = self.agent.get_all_relations()
			triplets_pred.sort()

			if triplets_pred != triplets_truth:
				diff = list(item for item in ndiff(triplets_truth, triplets_pred) if item[0] != ' ')
				if previous_diff == diff:
					report.append(Result(time_step["time"], "state", time_step["type"], True))
					print("Conflicting expected and predicted state (same as last discrepancy)")
				elif set(diff).issubset(set(previous_diff)):
					report.append(Result(time_step["time"], "state", time_step["type"], True))
					print("Conflicting expected and predicted state (fixed part of last discrepancy)")
				else:
					report.append(Result(time_step["time"], "state", time_step["type"], False))
					print("Conflicting expected and predicted state")
					with open(os.path.join(self.log_dir, f"{time_step['time']:04d}_state.diff"), "w") as f:
						f.write("\n".join(diff))
					with open(os.path.join(self.log_dir, f"{time_step['time']:04d}_state.expected"), "w") as f:
						f.write("\n".join(triplets_truth))
					with open(os.path.join(self.log_dir, f"{time_step['time']:04d}_state.predicted"), "w") as f:
						f.write("\n".join(triplets_pred))
				previous_diff = diff
			else:
				report.append(Result(time_step["time"], "state", time_step["type"], True))
				previous_diff = []
				print("Update successful")
			
		print("\nAll updates/goals processed")

		with open(os.path.join(self.log_dir, "report.txt"), "w") as f:
			f.write("\n".join(str(result) for result in report))
		self.agent.close()
		# os.system('sudo -u postgres psql -c "drop database knowledge_base"')

class Result:
	def __init__(self, time: int, result_type: str, time_step_type: str, success: bool) -> None:
		self.time = time
		self.result_type = result_type
		self.time_step_type = time_step_type
		self.success = success
	
	def __str__(self) -> str:
		return f"{self.time:04d}|{self.result_type}|{self.time_step_type}|{'Success' if self.success else 'Fail'}"

	@staticmethod
	def from_str(line: str) -> Result:
		args = line.split('|')
		assert len(args) == 4
		return Result(int(args[0]), args[1], args[2], args[3] == "Success")

if __name__ == "__main__":
	class Logger(IO):
		def __init__(self, file_path):
			self.terminal = sys.stdout
			self.log = open(file_path, "w")
		def write(self, message):
			self.terminal.write(message)
			self.log.write(message)  
		def flush(self):
			self.terminal.flush()
			self.log.flush()
		def close(self):
			self.log.close()

	experiment_dir = "experiment"
	domain_path = f"{experiment_dir}/domains/domain1"
	run_dir = f"{experiment_dir}/runs/gpt-4/rag+check"
	log = Logger(f"{run_dir}/output.log")
	with redirect_stdout(log):
		sim = KGSim(Dataset(domain_path), KGAgent(run_dir, True, True), run_dir)
		sim.run()
	log.close()