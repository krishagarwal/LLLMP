from __future__ import annotations
from abc import ABC, abstractmethod

import os
import psycopg2
from pathlib import Path
from difflib import ndiff

from dataset.simulation import Dataset

from knowledge_representation.knowledge_loader import load_knowledge_from_yaml, populate_with_knowledge # type: ignore
from knowledge_representation._libknowledge_rep_wrapper_cpp import LongTermMemoryConduit

from knowledge_graph.load_graph import load_graph
from knowledge_graph.agent import KGBaseAgent, KGAgent

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
				predicted_plan = self.agent.answer_planning_query(time_step["goal"])
				print("Generated plan")

				plan_file = "predicted_plan.pddl"
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
					with open(os.path.join(self.log_dir, f"{time_step['time']:02d}_plan.diff"), "w") as f:
						f.write("\n".join(ndiff(true_plan, predicted_plan)))
				else:
					print("Plan is correct")
			else:
				continue
			
			script = os.path.join(os.path.dirname(__file__), "knowledge_graph/configure_postgresql.sh")
			os.system(f"{script} password knowledge_base_truth >/dev/null 2>&1")

			all_knowledge = [load_knowledge_from_yaml(time_step["knowledge_path"])]
			populate_with_knowledge(LongTermMemoryConduit("knowledge_base_truth", "localhost"), all_knowledge)
			load_graph("knowledge_base_truth", "knowledge_graph")

			conn = psycopg2.connect(dbname="knowledge_base_truth", user="postgres", password="password", host="localhost", port=5432)
			cur = conn.cursor()
			cur.execute(f"LOAD 'age'")
			cur.execute(f"SET search_path = ag_catalog, '$user', public;")
			
			cur.execute("SELECT * from cypher('knowledge_graph', $$MATCH (V)-[R]->(V2) RETURN V.name, type(R), V2.name$$) as (subj agtype, rel agtype, obj agtype);")
			triplets_truth = [" -> ".join(row) for row in cur.fetchall() if all(isinstance(s, str) for s in row)]
			triplets_truth.sort()
			cur.close()
			conn.close()

			triplets_pred = self.agent.get_all_relations()
			triplets_pred.sort()

			if triplets_pred != triplets_truth:
				diff = list(item for item in ndiff(triplets_truth, triplets_pred) if item[0] != ' ')
				print("Conflicting expected and predicted state", "(same as last discrepancy)" if previous_diff == diff else "")
				with open(os.path.join(self.log_dir, f"{time_step['time']:02d}_state.diff"), "w") as f:
					f.write("\n".join(diff))
				with open(os.path.join(self.log_dir, f"{time_step['time']:02d}_state.expected"), "w") as f:
					f.write("\n".join(triplets_truth))
				with open(os.path.join(self.log_dir, f"{time_step['time']:02d}_state.predicted"), "w") as f:
					f.write("\n".join(triplets_pred))
				previous_diff = diff
			else:
				print("Update successful")
			
		print("\nAll updates/goals processed")
		self.agent.close()

if __name__ == "__main__":
	sim = KGSim(Dataset("test"), KGAgent("output"), "output")
	sim.run()