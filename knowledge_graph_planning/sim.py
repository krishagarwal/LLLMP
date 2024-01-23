from __future__ import annotations
from abc import ABC, abstractmethod

import os
import re
import tempfile

import psycopg2

from dataset.simulation import Dataset

from knowledge_representation.knowledge_loader import load_knowledge_from_yaml, populate_with_knowledge # type: ignore
from knowledge_representation._libknowledge_rep_wrapper_cpp import LongTermMemoryConduit

from knowledge_graph.load_graph import load_graph
from knowledge_graph.agent import KGBaseAgent, KGAgent

"""
SELECT * from cypher('knowledge_graph', $$ MATCH (V)-[R]-(V2) RETURN V.name, type(R), V2.name$$) as (subj agtype, rel agtype, obj agtype);
"""

# set API key
openai_keys_file = os.path.join(os.getcwd(), "keys/openai_keys.txt")
with open(openai_keys_file, "r") as f:
	keys = f.read()
keys = keys.strip().split('\n')
os.environ["OPENAI_API_KEY"] = keys[0]

class KGSim:
	def __init__(self, dataset: Dataset, agent: KGBaseAgent) -> None:
		self.dataset = dataset
		self.agent = agent
	
	def run(self):
		print(f"Initial State:\n{self.dataset.initial_state}")
		self.agent.input_initial_state(self.dataset.initial_state, self.dataset.initial_knowledge_yaml, self.dataset.predicate_names)
		for time_step in self.dataset:
			if time_step["type"] == "state_change":
				print("\nTime: " + str(time_step["time"]))
				print(f"State change: {time_step['state_change']}")
				output = self.agent.input_state_change(time_step["state_change"])
				print("Completed state change")

				script = os.path.join(os.path.dirname(__file__), "knowledge_graph/configure_postgresql.sh")
				os.system(f"{script} password knowledge_base_truth >/dev/null 2>&1")
				with tempfile.NamedTemporaryFile(mode='w') as temp_yaml_file:
					temp_yaml_file.write(time_step["knowledge_yaml"])
					all_knowledge = [load_knowledge_from_yaml(temp_yaml_file.name)]
				populate_with_knowledge(LongTermMemoryConduit("knowledge_base_truth", "localhost"), all_knowledge)
				load_graph("knowledge_base_truth", "knowledge_graph")

				conn = psycopg2.connect(dbname="knowledge_base_truth", user="postgres", password="password", host="localhost", port=5432)
				cur = conn.cursor()
				cur.execute(f"LOAD 'age'")
				cur.execute(f"SET search_path = ag_catalog, '$user', public;")
				
				cur.execute("SELECT * from cypher('knowledge_graph', $$MATCH (V)-[R]->(V2) RETURN V.name, type(R), V2.name$$) as (subj agtype, rel agtype, obj agtype);")
				triplets_truth = [" -> ".join(row) for row in cur.fetchall()]
				triplets_truth.sort()
				cur.close()
				conn.close()

				triplets_pred = self.agent.get_all_relations()
				triplets_pred.sort()

				if triplets_pred != triplets_truth:
					print("Failed state change")
					print(output)
					print("---------------------")
					print("EXPECTED TRIPLETS:")
					print("\n".join(triplets_truth))
					print("---------------------")
					print("PREDICTED TRIPLETS:")
					print("\n".join(triplets_pred))
					self.agent.close()
					return
				print("State change successful")
		print("\nAll state changes successful")
		self.agent.close()

if __name__ == "__main__":
	sim = KGSim(Dataset("test"), KGAgent())
	sim.run()