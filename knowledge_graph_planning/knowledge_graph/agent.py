from __future__ import annotations
from abc import ABC, abstractmethod
from functools import partial

import os
import re
import time
from contextlib import redirect_stdout
from pathlib import Path

from numpy import require

from knowledge_representation import get_default_ltmc # type: ignore
from knowledge_representation.knowledge_loader import load_knowledge_from_yaml, populate_with_knowledge # type: ignore
from knowledge_graph.load_graph import load_graph
from knowledge_graph.age import AgeGraphStore

from llama_index.prompts import PromptTemplate, PromptType
from llama_index import ServiceContext
from llama_index.storage.storage_context import StorageContext
from llama_index.llms import OpenAI
from llama_index.retrievers import KnowledgeGraphRAGRetriever
from llama_index.query_engine import RetrieverQueryEngine

from knowledge_graph.utils import get_prompt_template, extract_keywords

from pddl_parser.PDDL import PDDL_Parser, Action

class KGBaseAgent(ABC):
	@abstractmethod
	def input_initial_state(self, initial_state: str, knowledge_yaml_file: str, predicate_names: list[str], domain_pddl_file: str) -> str:
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

	@abstractmethod
	def answer_planning_query(self, query: str) -> list[str]:
		pass

class KGAgent(KGBaseAgent):
	def __init__(self, log_dir: str) -> None:
		self.log_dir = log_dir
		self.dbname = "knowledge_base"
		self.dbuser = "postgres"
		self.dbpass = "password"
		self.dbhost = "localhost"
		self.dbport = 5432
		self.graph_name = "knowledge_graph"
		self.time = 0
	
	def input_initial_state(self, initial_state: str, knowledge_path: str, predicate_names: list[str], domain_path: str) -> None:
		os.system(f"$(rospack find knowledge_representation)/scripts/configure_postgresql.sh {self.dbpass} >/dev/null 2>&1")
		all_knowledge = [load_knowledge_from_yaml(knowledge_path)]
		populate_with_knowledge(get_default_ltmc(), all_knowledge)

		load_graph(self.dbname, self.graph_name)

		graph_name = "knowledge_graph"
		self.graph_store = AgeGraphStore(
			dbname=self.dbname,
			user=self.dbuser,
			password=self.dbpass,
			host=self.dbhost,
			port=self.dbport,
			graph_name=graph_name,
			node_label="entity"
		)
		
		self.cur = self.graph_store.cursor()
		self.cur.execute(f"LOAD 'age';")
		self.cur.execute(f"SET search_path = ag_catalog, '$user', public;")
		
		# get all the entity_names (used for entity selection)
		entity_names_query = """SELECT attribute_value "name" FROM entities
			JOIN entity_attributes_str ON entities.entity_id = entity_attributes_str.entity_id
			WHERE attribute_name = 'name';
		"""
		self.cur.execute(entity_names_query)
		entity_list = [row[0] for row in self.cur.fetchall()]

		self.entity_types = {}

		for entity in entity_list:
			instance_of_query = (f"SELECT * from cypher('{self.graph_name}'," 
									f"$$MATCH (u:entity {{name: '{entity}'}})-[e:instance_of]->(v)"
									f"return v.name$$) as (v agtype);")
			self.cur.execute(instance_of_query)
			self.entity_types[entity] = self.cur.fetchall()[0][0][1:-1] # remove quotes
		
		entity_names = ", ".join(entity_list)

		# load in all default prompts
		ENTITY_SELECT_PROMPT = get_prompt_template("prompts/entity_select_prompt.txt", entity_names=entity_names)
		self.TRIPLET_FILTER_PROMPT = get_prompt_template("prompts/triplet_filter_prompt.txt")
		self.TRIPLET_UPDATE_PROMPT = get_prompt_template("prompts/triplet_update_prompt.txt",
											predicate_names=", ".join(predicate_names), entity_names=entity_names)

		self.llm = OpenAI(temperature=0, model="gpt-4")
		service_context = ServiceContext.from_defaults(llm=self.llm)
		storage_context = StorageContext.from_defaults(graph_store=self.graph_store)
		self.rag_update_retriever = KnowledgeGraphRAGRetriever(
			storage_context=storage_context,
			service_context=service_context,
			llm=self.llm,
			verbose=False,
			graph_traversal_depth=2,
			max_knowledge_sequence=100,
			entity_extract_fn=partial(extract_keywords, service_context, ENTITY_SELECT_PROMPT),
			synonym_expand_fn=(lambda _ : [])
		)

		pddl_parser = PDDL_Parser()
		pddl_parser.parse_domain(domain_path)
		self.pddl_actions : dict[str, Action] = {}
		for action in pddl_parser.actions:
			self.pddl_actions[action.name] = action

		self.domain_path = domain_path
		with open(self.domain_path, "r") as f:
			domain_pddl = f.read()

		template = get_prompt_template("prompts/plan_entity_select_prompt.txt", domain_pddl=domain_pddl, entity_names=entity_names)
		self.PLAN_QUERY_TEMPLATE = get_prompt_template("prompts/plan_query_prompt.txt", domain_pddl=domain_pddl)

		self.rag_plan_retriever = KnowledgeGraphRAGRetriever(
			storage_context=storage_context,
			service_context=service_context,
			verbose=True,
			graph_traversal_depth=2,
			max_knowledge_sequence=500,
			max_entities=10,
			entity_extract_fn=partial(extract_keywords, service_context, template),
			entity_extract_policy="union"
		)
		self.query_engine = RetrieverQueryEngine.from_args(
			self.rag_plan_retriever, service_context=service_context
		)
	
	# format triplets from query output
	@staticmethod
	def postprocess_triplet(triplet: str) -> str:
		components = [re.sub(r'[^a-zA-Z0-9_]', '', component) for component in triplet.split(", ")]
		return " -> ".join(components)

	def input_state_change(self, state_change: str) -> None:
		log_file = os.path.join(self.log_dir, f"state_change_{self.time:02d}.log")
		with open(log_file, "w") as f:
			f.write(f"STATE CHANGE: {state_change}\n")
		
			context_nodes = self.rag_update_retriever.retrieve(state_change)
			context_str = context_nodes[0].text if len(context_nodes) > 0 else "None"
			triplets = [KGAgent.postprocess_triplet(triplet) for triplet in context_str.split('\n')[2:]]
			triplet_str = '\n'.join(triplets)

			f.write("------------------------------------------------\n")
			f.write("EXTRACTED TRIPLETS:\n\n")
			f.write(triplet_str + "\n")

			# filter out irrelevant triplets using LLM directly
			filtered_triplet_str = self.llm.complete(self.TRIPLET_FILTER_PROMPT.format(state_change=state_change, triplet_str=triplet_str)).text
			f.write("------------------------------------------------\n")
			f.write("FILTERED TRIPLETS:\n\n")
			f.write(filtered_triplet_str + "\n")

			# query LLM to update triplets (remove existing and add new)
			triplet_updates = self.llm.complete(self.TRIPLET_UPDATE_PROMPT.format(state_change=state_change, filtered_triplet_str=filtered_triplet_str)).text
			f.write("------------------------------------------------\n")
			f.write("TRIPLETS TO ADD AND REMOVE\n\n")
			f.write(triplet_updates + "\n")

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
				self.graph_store.delete(triplet[0], triplet[1], triplet[2])

		# add new triplets to graph
		for triplet_str in add:
			triplet = triplet_str.split(" -> ")
			if len(triplet) == 3:
				self.graph_store.upsert_triplet(triplet[0], triplet[1], triplet[2])
		
		self.time += 1
	
	def answer_planning_query(self, query: str) -> list[str]:
		# A. generate problem pddl file
		log_file = os.path.join(self.log_dir, f"plan_query_{self.time}.log")

		with open(log_file + ".context.log", "w") as f:
			f.write(query + "\n")
			with redirect_stdout(f):
				nodes = self.query_engine.retrieve("I have a task for the robot: " + query) # type: ignore

		# objects = set(["me"])
		# constants = {'Cold', 'Hot', 'RoomTemp', 'Water', 'Coffee', 'Wine'}
		init_block = "\t(:init\n"
		for rel in nodes[0].metadata['kg_rel_text']:
			predicate = rel.split('-[')[1].split(']')[0]
			arg1 = rel.split(',')[0]
			arg2 = rel.split('-> ')[1]
			if predicate == "instance_of" or predicate == "room_has":
				continue
			elif arg2 == 'True':
				init_block += f"\t\t({predicate} {arg1})\n"
				# if arg1 != "Robot":
				# 	objects.add(arg1)
			elif arg2 == 'None' or arg2 == 'False':
				continue
			else:
				init_block += f"\t\t({predicate} {arg1} {arg2})\n"
				# if arg1 != "Robot":
				# 	objects.add(arg1)
				# objects.add(arg2)
				# if arg2 not in constants:
				# 	objects.add(arg2)
		init_block += "\t)\n"
		objects_block = "\t(:objects\n"
		for obj, obj_type in self.entity_types.items():
			objects_block += f"\t\t{obj} - {obj_type}\n"
		objects_block += "\t)\n"

		plan_query_prompt = self.PLAN_QUERY_TEMPLATE.format(task_nl=query)
		goal_block = self.query_engine._response_synthesizer.synthesize(query=plan_query_prompt, nodes=nodes).response # type:ignore

		task_pddl_ = f"(define (problem p{self.time})\n" + \
					 f"\t(:domain simulation)\n" + \
					 objects_block + \
					 init_block + \
					 f"\t{goal_block}\n)"

		# B. write the problem file into the problem folder
		task_pddl_file_name = self.log_dir + f"/problem_{self.time:02d}.pddl"
		with open(task_pddl_file_name, "w") as f:
			f.write(task_pddl_)
		time.sleep(1)

		# C. run lapkt to plan
		plan_file_name = self.log_dir + f"/plan_{self.time:02d}.pddl"

		project_dir = Path(__file__).parent.parent.parent.as_posix()
		os.system(f"sudo docker run --rm -v {project_dir}:/root/experiments lapkt/lapkt-public ./siw-then-bfsf " + \
				  f"--domain /root/experiments/{self.domain_path} " + \
				  f"--problem /root/experiments/{task_pddl_file_name} " + \
				  f"--output /root/experiments/{plan_file_name} " + \
				  f"> {log_file}.pddl.log")
		
		with open(plan_file_name, "r") as f:
			plan = f.read().splitlines()
			self.process_plan(plan)

		self.time += 1

		return plan
	
	def process_plan(self, plan: list[str]):
		for item in plan:
			tokens = item[1:-1].lower().split()
			action_name, args = tokens[0], tokens[1:]
			action = self.pddl_actions[action_name]

			assert len(args) == len(action.parameters)
			param_names = {}
			for token, name in zip(action.parameters, args):
				param_names[token[0]] = name
						
			for del_effect in action.del_effects:
				predicate, required_params = del_effect[0], del_effect[1:]
				if len(required_params) == 2:
					arg1 = param_names[required_params[0]]
					arg2 = param_names[required_params[1]]
					self.graph_store.delete(arg1, predicate, arg2)
				elif len(required_params) == 1:
					arg = param_names[required_params[0]]
					self.graph_store.delete(arg, predicate, True) # type: ignore
					self.graph_store.upsert_triplet_bool(arg, predicate, False) # type: ignore

			for add_effect in action.add_effects:
				predicate, required_params = add_effect[0], add_effect[1:]
				if len(required_params) == 2:
					arg1 = param_names[required_params[0]]
					arg2 = param_names[required_params[1]]
					self.graph_store.upsert_triplet(arg1, predicate, arg2)
				elif len(required_params) == 1:
					arg = param_names[required_params[0]]
					self.graph_store.delete(arg, predicate, False) # type: ignore
					self.graph_store.upsert_triplet_bool(arg, predicate, True) # type: ignore

	
	def get_all_relations(self) -> list[str]:
		self.cur.execute("SELECT * from cypher('knowledge_graph', $$MATCH (V)-[R]->(V2) RETURN V.name, type(R), V2.name$$) as (subj agtype, rel agtype, obj agtype);")
		return [" -> ".join(row) for row in self.cur.fetchall() if all(isinstance(s, str) for s in row)]
	
	def close(self) -> None:
		self.cur.close()

