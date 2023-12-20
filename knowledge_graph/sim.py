from __future__ import annotations
from abc import ABC, abstractmethod

import os
import sys
import re
import tempfile

import psycopg2

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from dataset.simulation import Dataset
from knowledge_representation import get_default_ltmc # type: ignore
from knowledge_representation.knowledge_loader import load_knowledge_from_yaml, populate_with_knowledge # type: ignore
from knowledge_representation._libknowledge_rep_wrapper_cpp import LongTermMemoryConduit

from age import AgeGraphStore
from load_graph import load_graph

from llama_index.prompts import PromptTemplate, PromptType
from llama_index import ServiceContext
from llama_index.storage.storage_context import StorageContext
from llama_index.llms import OpenAI
from llama_index.retrievers import KnowledgeGraphRAGRetriever

"""
SELECT * from cypher('knowledge_graph', $$ MATCH (V)-[R]-(V2) RETURN V.name, type(R), V2.name$$) as (subj agtype, rel agtype, obj agtype);
"""

# set API key
openai_keys_file = os.path.join(os.getcwd(), "keys/openai_keys.txt")
with open(openai_keys_file, "r") as f:
	keys = f.read()
keys = keys.strip().split('\n')
os.environ["OPENAI_API_KEY"] = keys[0]

class KGBaseAgent(ABC):
	@abstractmethod
	def input_initial_state(self, initial_state: str, knowledge_yaml: str, predicate_names: list[str]) -> str:
		pass

	@abstractmethod
	def input_state_change(self, state_change: str) -> None:
		pass

	@abstractmethod
	def get_all_relations(self) -> list[str]:
		pass

	@abstractmethod
	def close(self) -> None:
		pass

class KGAgent(KGBaseAgent):

	# read prompt template from file and format
	@staticmethod
	def get_prompt_template(filename: str, **kwargs) -> str:
		with open(os.path.join(os.path.dirname(__file__), filename), "r") as f:
			contents = f.read()
		if not kwargs:
			return contents
		return contents.format(**kwargs)
	
	def input_initial_state(self, initial_state: str, knowledge_yaml: str, predicate_names: list[str]) -> None:
		os.system("$(rospack find knowledge_representation)/scripts/configure_postgresql.sh password")
		with tempfile.NamedTemporaryFile(mode='w') as temp_yaml_file:
			temp_yaml_file.write(knowledge_yaml)
			all_knowledge = [load_knowledge_from_yaml(temp_yaml_file.name)]
		populate_with_knowledge(get_default_ltmc(), all_knowledge)

		load_graph("knowledge_base", "knowledge_graph")

		graph_name = "knowledge_graph"
		graph_store = AgeGraphStore(
			dbname="knowledge_base",
			user="postgres",
			password="password",
			host="localhost",
			port=5432,
			graph_name=graph_name,
			node_label="entity"
		)
		self.conn = graph_store.client()
		self.conn.autocommit = True
		
		# Create a new database session and return a new instance of the connection class
		self.cur = self.conn.cursor()
		self.cur.execute(f"LOAD 'age';")
		self.cur.execute(f"SET search_path = ag_catalog, '$user', public;")
		
		# get all the entity_names (used for entity selection)
		entity_names_query = """
		SELECT entities.entity_id, attribute_value "name" FROM entities
			JOIN entity_attributes_str ON entities.entity_id = entity_attributes_str.entity_id
			WHERE attribute_name = 'name';
		"""
		self.cur.execute(entity_names_query)
		entity_names = ", ".join([row[1] for row in self.cur.fetchall()])

		# load in all default prompts
		ENTITY_SELECT_TEMPLATE = KGAgent.get_prompt_template("prompts/entity_select_prompt.txt", entity_names=entity_names)
		ENTITY_SELECT_PROMPT = PromptTemplate(
			ENTITY_SELECT_TEMPLATE,
			prompt_type=PromptType.QUERY_KEYWORD_EXTRACT,
		)
		self.TRIPLET_FILTER_PROMPT = KGAgent.get_prompt_template("prompts/triplet_filter_prompt.txt")
		self.TRIPLET_UPDATE_PROMPT = KGAgent.get_prompt_template("prompts/triplet_update_prompt.txt", predicate_names=", ".join(predicate_names))

		self.llm = OpenAI(temperature=0, model="gpt-4")
		service_context = ServiceContext.from_defaults(llm=self.llm)
		storage_context = StorageContext.from_defaults(graph_store=graph_store)
		self.graph_rag_retriever = KnowledgeGraphRAGRetriever(
			storage_context=storage_context,
			service_context=service_context,
			llm=self.llm,
			verbose=False,
			graph_traversal_depth=2,
			max_knowledge_sequence=100,
			entity_extract_template=ENTITY_SELECT_PROMPT,
			synonym_expand_fn=(lambda _ : [])
		)
	
	# format triplets from query output
	@staticmethod
	def postprocess_triplet(triplet: str) -> str:
		components = [re.sub(r'[^a-zA-Z0-9_]', '', component) for component in triplet.split(", ")]
		return " -> ".join(components)

	def input_state_change(self, state_change: str) -> str:
		output = "------------------------------------------------\n"
		output += f"STATE CHANGE: {state_change}\n"
	
		context_nodes = self.graph_rag_retriever.retrieve(state_change)
		context_str = context_nodes[0].text if len(context_nodes) > 0 else "None"
		triplets = [KGAgent.postprocess_triplet(triplet) for triplet in context_str.split('\n')[2:]]
		triplet_str = '\n'.join(triplets)

		output += "------------------------------------------------\n"
		output += "EXTRACTED TRIPLETS:\n\n"
		output += triplet_str + "\n"

		# filter out irrelevant triplets using LLM directly
		filtered_triplet_str = self.llm.complete(self.TRIPLET_FILTER_PROMPT.format(state_change=state_change, triplet_str=triplet_str)).text
		output += "------------------------------------------------\n"
		output += "FILTERED TRIPLETS:\n\n"
		output += filtered_triplet_str + "\n"

		# query LLM to update triplets (remove existing and add new)
		triplet_updates = self.llm.complete(self.TRIPLET_UPDATE_PROMPT.format(state_change=state_change, filtered_triplet_str=filtered_triplet_str)).text
		output += "------------------------------------------------\n"
		output += "TRIPLETS TO ADD AND REMOVE\n\n"
		output += triplet_updates + "\n"
		output += "------------------------------------------------\n"

		# process the changes and commit to knowledge graph
		print(triplet_updates)
		update_lines = triplet_updates.split('\n')
		remove_idx = update_lines.index("REMOVE:")
		add_idx = update_lines.index("ADD:")
		remove = update_lines[remove_idx + 1 : add_idx]
		add = update_lines[add_idx + 1:]

		# delete triplets from graph
		for triplet_str in remove:
			triplet = triplet_str.split(" -> ")
			if len(triplet) == 3:
				self.cur.execute(f"SELECT * FROM cypher('knowledge_graph', $$MATCH (u {{name: '{triplet[0]}'}})-[e:{triplet[1]}]->(v {{name: '{triplet[2]}'}}) DELETE e$$) as (e agtype);")

		# add new triplets to graph
		for triplet_str in add:
			triplet = triplet_str.split(" -> ")
			if len(triplet) == 3:
				self.cur.execute(f"SELECT * FROM cypher('knowledge_graph', $$MATCH (u {{name: '{triplet[0]}'}}), (v {{name: '{triplet[2]}'}}) CREATE (u)-[e:{triplet[1]}]->(v) RETURN e$$) as (e agtype);")

		return output
	
	def get_all_relations(self) -> list[str]:
		self.cur.execute("SELECT * from cypher('knowledge_graph', $$MATCH (V)-[R]->(V2) RETURN V.name, type(R), V2.name$$) as (subj agtype, rel agtype, obj agtype);")
		return [" -> ".join(row) for row in self.cur.fetchall()]
	
	def close(self) -> None:
		self.cur.close()
		self.conn.close()

class KGSim:
	def __init__(self, dataset: Dataset, agent: KGBaseAgent) -> None:
		self.dataset = dataset
		self.agent = agent
	
	def run(self):
		print(f"Initial State:\n{self.dataset.initial_state}")
		self.agent.input_initial_state(self.dataset.initial_state, self.dataset.initial_knowledge_yaml, self.dataset.predicate_names)
		for time_step in self.dataset:
			print("Time: " + str(time_step["time"]))
			if time_step["type"] == "state_change":
				print(f"\nState change: {time_step['state_change']}")
				output = self.agent.input_state_change(time_step["state_change"])
				print("Completed state change")

				script = os.path.join(os.path.dirname(__file__), "configure_postgresql.sh")
				os.system(f"{script} password knowledge_base_truth")
				with tempfile.NamedTemporaryFile(mode='w') as temp_yaml_file:
					temp_yaml_file.write(time_step["knowledge_yaml"])
					all_knowledge = [load_knowledge_from_yaml(temp_yaml_file.name)]
				populate_with_knowledge(LongTermMemoryConduit("knowledge_base_truth"), all_knowledge)
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
		self.agent.close()

if __name__ == "__main__":
	sim = KGSim(Dataset("test"), KGAgent())
	sim.run()