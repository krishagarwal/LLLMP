from __future__ import annotations
from abc import ABC, abstractmethod

import os
import tempfile
import re

from knowledge_representation import get_default_ltmc # type: ignore
from knowledge_representation.knowledge_loader import load_knowledge_from_yaml, populate_with_knowledge # type: ignore
from knowledge_graph.load_graph import load_graph
from knowledge_graph.age import AgeGraphStore

from llama_index.prompts import PromptTemplate, PromptType
from llama_index import ServiceContext
from llama_index.storage.storage_context import StorageContext
from llama_index.llms import OpenAI
from llama_index.retrievers import KnowledgeGraphRAGRetriever

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
		os.system("$(rospack find knowledge_representation)/scripts/configure_postgresql.sh password >/dev/null 2>&1")
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
		self.TRIPLET_UPDATE_PROMPT = KGAgent.get_prompt_template("prompts/triplet_update_prompt.txt",
											predicate_names=", ".join(predicate_names), entity_names=", ".join(entity_names))

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