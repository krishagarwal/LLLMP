from __future__ import annotations
from abc import ABC, abstractmethod
from functools import partial

import itertools
import os
import re
import time
from contextlib import redirect_stdout
from pathlib import Path
import json

import tiktoken

from knowledge_representation import get_default_ltmc # type: ignore
from knowledge_representation.knowledge_loader import load_knowledge_from_yaml, populate_with_knowledge # type: ignore
from knowledge_graph.load_graph import load_graph
from knowledge_graph.age import AgeGraphStore

from llama_index.core import ServiceContext
from llama_index.core.storage.storage_context import StorageContext
from llama_index.llms.openai import OpenAI
from llama_index.core.retrievers import KnowledgeGraphRAGRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.llms.openai.base import ChatMessage

from .utils import get_prompt_template, extract_keywords
from .chat_mem_buffer import TripletTrimBuffer

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
	def answer_planning_query(self, query: str, truth_graph_store: AgeGraphStore) -> list[str]:
		pass

class KGAgent(KGBaseAgent):
	MAX_RETRY_STATE_CHANGE = 5

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
		) # type: ignore
		
		cur = self.graph_store.cursor()
		
		# get all the entity_names (used for entity selection)
		entity_names_query = """SELECT attribute_value "name" FROM entities
			JOIN entity_attributes_str ON entities.entity_id = entity_attributes_str.entity_id
			WHERE attribute_name = 'name';
		"""
		cur.execute(entity_names_query)
		entity_list = [row[0] for row in cur.fetchall()]

		instance_of_query = ("SELECT * from instance_of")
		cur.execute(instance_of_query)
		self.entity_types = {self.graph_store.id_to_name[row[0]] : row[1] for row in cur.fetchall() if row[0] in self.graph_store.id_to_name}
		self.entity_list = list(self.entity_types.keys())
		cur.close()	
		entity_names = ", ".join(entity_list)

		pddl_parser = PDDL_Parser()
		pddl_parser.parse_domain(domain_path)
		self.pddl_actions : dict[str, Action] = {}
		for action in pddl_parser.actions:
			self.pddl_actions[action.name] = action
		
		self.pddl_supertypes: dict[str, list[str]] = {}
		for supertype in pddl_parser.types:
			if supertype not in self.pddl_supertypes:
				self.pddl_supertypes[supertype] = [supertype]
			for type in pddl_parser.types[supertype]:
				if type not in self.pddl_supertypes:
					self.pddl_supertypes[type] = [type]
				self.pddl_supertypes[type] += self.pddl_supertypes[supertype]
		
		self.pddl_predicates = pddl_parser.predicates
		for pred in self.pddl_predicates:
			args = self.pddl_predicates[pred]
			for arg in args:
				if isinstance(args[arg], str):
					args[arg] = [args[arg]]
				else:
					args[arg].remove("either")

		self.entities_by_type: dict[str, list[str]] = {}
		for entity, entity_type in self.entity_types.items():
			for supertype in self.pddl_supertypes[entity_type]:
				if supertype not in self.entities_by_type:
					self.entities_by_type[supertype] = []
				self.entities_by_type[supertype].append(entity)

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
			verbose=True,
			graph_traversal_depth=3,
			max_knowledge_sequence=100,
			entity_extract_fn=partial(extract_keywords, service_context, ENTITY_SELECT_PROMPT),
			synonym_expand_fn=(lambda _: []),
			entity_extract_template=None,
			synonym_expand_template=None,
		)
		self.rag_update_retriever._entity_extract_template = None # type: ignore
		self.rag_update_retriever._synonym_expand_template = None # type: ignore

		self.domain_path = domain_path
		with open(self.domain_path, "r") as f:
			domain_pddl = f.read()

		PLAN_ENTITY_SELECT_PROMPT = get_prompt_template("prompts/plan_entity_select_prompt.txt", domain_pddl=domain_pddl, entity_names=entity_names)
		self.PLAN_QUERY_TEMPLATE = get_prompt_template("prompts/plan_query_prompt.txt", domain_pddl=domain_pddl)

		rag_plan_service_context = ServiceContext.from_defaults(
			llm=OpenAI(temperature=0, model="gpt-4")
		)
		self.rag_plan_retriever = KnowledgeGraphRAGRetriever(
			storage_context=storage_context,
			service_context=rag_plan_service_context,
			verbose=True,
			graph_traversal_depth=3,
			max_knowledge_sequence=300,
			max_entities=10,
			entity_extract_fn=partial(extract_keywords, rag_plan_service_context, PLAN_ENTITY_SELECT_PROMPT),
			synonym_expand_fn=(lambda _: []),
			entity_extract_template=None,
			synonym_expand_template=None,
		)
		self.rag_plan_retriever._entity_extract_template = None # type: ignore
		self.rag_plan_retriever._synonym_expand_template = None # type: ignore

		self.query_engine = RetrieverQueryEngine.from_args(
			self.rag_plan_retriever, service_context=rag_plan_service_context
		)
	
	# format triplets from query output
	@staticmethod
	def postprocess_triplet(triplet: str) -> str:
		components = [re.sub(r'[^a-zA-Z0-9_]', '', component) for component in triplet.split(", ")]
		return " -> ".join(components)
	
	@staticmethod
	def is_divider_str(triplet_str: str) -> bool:
		return all(c == '-' for c in triplet_str)
	
	def get_relation_issues(self, subj: str, rel: str, obj: str) -> list[str]:
		triplet_str = f"{subj} -> {rel} -> {obj}"
		issues = []
		obj_is_bool = (obj == "true" or obj == "false")
		components_valid = True
		
		if rel not in self.pddl_predicates:
			issues.append(f"`{rel}` is not a valid relation in `{triplet_str}`. You may need to use a different relation or this relation may not be necessary to add.")
			components_valid = False
		if subj not in self.entity_types:
			issues.append(f"`{subj}` is not a valid entity in `{triplet_str}`")
			components_valid = False
		if not obj_is_bool and obj not in self.entity_types:
			issues.append(f"`{obj}` is not a valid entity in `{triplet_str}`")
			components_valid = False
		if not components_valid:
			return issues

		arg_types = self.pddl_predicates[rel]
		if (obj_is_bool ^ len(arg_types) == 1) or not any(x in self.pddl_supertypes[self.entity_types[subj]] for x in arg_types["?a"]) or (not obj_is_bool and not any(x in self.pddl_supertypes[self.entity_types[obj]] for x in arg_types["?b"])):
			allowed_subj_types = "|".join(arg_types["?a"])
			allowed_obj_types = "true|false" if len(arg_types) == 1 else "|".join(arg_types["?b"])
			issues.append(f"Invalid use of `{rel}` in `{triplet_str}`. Can only apply `{rel}` with types: [{allowed_subj_types}] -> {rel} -> [{allowed_obj_types}]")
		return issues

	def input_state_change(self, state_change: str) -> None:
		context_nodes = self.rag_update_retriever.retrieve(state_change)
		context_str = context_nodes[0].text if len(context_nodes) > 0 else "None"
		triplets = [KGAgent.postprocess_triplet(triplet) for triplet in context_str.split('\n')[2:]]
		# triplets = self.get_all_relations()
		extracted_triplets_str = '\n'.join(triplets)

		# filter out irrelevant triplets using LLM directly
		filtered_triplet_str = self.llm.complete(self.TRIPLET_FILTER_PROMPT.format(state_change=state_change, triplet_str=extracted_triplets_str)).text
		# filtered_triplet_str = extracted_triplets_str
		log = [f"STATE CHANGE: {state_change}", f"EXTRACTED TRIPLETS:\n{extracted_triplets_str}", f"FILTERED TRIPLETS:\n{filtered_triplet_str}"]

		update_issues = []
		remove = []
		add = []
		triplet_updates = ""

		triplet_update_prompt = self.TRIPLET_UPDATE_PROMPT.format(state_change=state_change)
		messages: list[ChatMessage] = []

		num_attempts = 0

		while num_attempts < KGAgent.MAX_RETRY_STATE_CHANGE and (update_issues or num_attempts == 0):
			if len(update_issues) > 0:
				curr_message = ChatMessage()
				curr_message.content = "There are some issues with your provided updates:\n * " + "\n * ".join(update_issues) + "\nPlease try again."
				messages.append(curr_message)
				log.append("UPDATE ISSUES:\n * " + "\n * ".join(update_issues))
				with open(os.path.join(self.log_dir, f"{self.time:04d}_state_change.messages.{num_attempts}"), "w") as f:
					f.write("\n===================================\n".join(log))
			
			update_issues = []
			num_attempts += 1
			print("Attempting state change...", num_attempts)

			# query LLM to update triplets (remove existing and add new)
			truncated_msgs = TripletTrimBuffer.from_defaults(messages, llm=self.llm, tokenizer_fn=tiktoken.encoding_for_model(self.llm.model).encode).get(triplet_update_prompt, triplets=filtered_triplet_str)
			curr_response = self.llm.chat(truncated_msgs).message
			messages.append(curr_response)
			triplet_updates = curr_response.content
			assert triplet_updates is not None
			log.append(triplet_updates)

			# process the changes and commit to knowledge graph
			try:
				start_idx = triplet_updates.index("{")
			except ValueError:
				update_issues.append("Your response was not in the correct JSON format")
				continue
			
			try:
				end_idx = triplet_updates.rindex("}")
			except ValueError:
				update_issues.append("Your response was not in the correct JSON format")
				continue
			
			triplet_updates = triplet_updates[start_idx : end_idx + 1]
			try:
				update_json = json.loads(triplet_updates)
			except json.decoder.JSONDecodeError:
				update_issues.append("Your response was not in the correct JSON format")
				continue
			
			bad_json = False

			if "ADD" not in update_json:
				update_issues.append("There was no 'ADD' entry in your provided JSON")
				bad_json = True
			elif not isinstance(update_json["ADD"], list):
				update_issues.append("The 'ADD' entry in your provided JSON did not contain a list")
				bad_json = True
			elif not all(isinstance(x, str) for x in update_json["ADD"]):
				update_issues.append("The 'ADD' entry in your provided JSON did not contain a list of triplet strings")
				bad_json = True
			
			if "REMOVE" not in update_json:
				update_issues.append("There was no 'REMOVE' entry in your provided JSON")
				bad_json = True
			elif not isinstance(update_json["REMOVE"], list):
				update_issues.append("The 'REMOVE' entry in your provided JSON did not contain a list")
				bad_json = True
			elif not all(isinstance(x, str) for x in update_json["REMOVE"]):
				update_issues.append("The 'REMOVE' entry in your provided JSON did not contain a list of triplet strings")
				bad_json = True
			
			if bad_json:
				continue
			
			remove = set(update_json["REMOVE"])
			add = set(update_json["ADD"])

			for triplet_str in add:
				triplet_str = str(triplet_str)
				triplet = triplet_str.split(" -> ")
				if len(triplet) != 3:
					update_issues.append(f"All relations must follow the following format: [subject] -> [relation] -> [object or boolean]. '{triplet_str}' does not follow this format.")
					continue
				
				subj, rel, obj = triplet[0], triplet[1], triplet[2]
				obj_is_bool = (obj == "true" or obj == "false")
				
				update_issues += self.get_relation_issues(subj, rel, obj)
				if update_issues:
					continue

				if obj_is_bool:
					expected_remove = "{} -> {} -> {}".format(subj, rel, "true" if obj == "false" else "false")
					if expected_remove not in remove:
						update_issues.append(f"Cannot add '{triplet_str}' without removing '{expected_remove}'")
						continue
				if self.graph_store.rel_exists(subj, rel, obj):
					update_issues.append(f"Cannot add '{triplet_str}' because it already exists in the graph")
				
			for triplet_str in remove:
				triplet = triplet_str.split(" -> ")
				if len(triplet) != 3:
					update_issues.append(f"All relations must follow the following format: [subject] -> [relation] -> [object or boolean]. `{triplet_str}` does not follow this format.")
					continue

				subj, rel, obj = triplet[0], triplet[1], triplet[2]

				if not self.graph_store.rel_exists(subj, rel, obj):
					update_issues.append(f"Cannot remove '{triplet_str}' because it does not exist in the graph")
					continue
				
				if obj == "true" or obj == "false":
					expected_add = "{} -> {} -> {}".format(subj, rel, "true" if obj == "false" else "false")
					if expected_add not in add:
						update_issues.append(f"Cannot remove '{triplet_str}' without adding '{expected_add}'")

		# log the state update
		log_file = os.path.join(self.log_dir, f"{self.time:04d}_state_change.log")
		with open(log_file, "w") as f:
			f.write("\n===================================\n".join(log))
		self.time += 1

		if update_issues:
			print("Could not resolve state change within maximum number of tries", KGAgent.MAX_RETRY_STATE_CHANGE)
			return

		# delete triplets from graph
		for triplet_str in remove:
			triplet = triplet_str.split(" -> ")
			if len(triplet) == 3:
				self.graph_store.delete(triplet[0], triplet[1], triplet[2])
				if triplet[2] == "true" or triplet[2] == "false":
					self.graph_store.upsert_triplet_bool(triplet[0], triplet[1], triplet[2] == "false")

		# add new triplets to graph
		for triplet_str in add:
			triplet = triplet_str.split(" -> ")
			if len(triplet) == 3:
				self.graph_store.upsert_triplet(triplet[0], triplet[1], triplet[2])
	
	def answer_planning_query(self, query: str, truth_graph_store: AgeGraphStore) -> list[str]:
		# A. generate problem pddl file
		log_file = os.path.join(self.log_dir, f"{self.time:04d}_plan_query")

		with open(log_file + ".context.log", "w") as f:
			f.write(query + "\n")
			with redirect_stdout(f):
				nodes = self.query_engine.retrieve("I have a task for the robot: " + query) # type: ignore

		# objects = set(["me"])
		# constants = {'Cold', 'Hot', 'RoomTemp', 'Water', 'Coffee', 'Wine'}
		init_block = "\t(:init\n"
		if len(nodes) > 0:
			for rel in nodes[0].metadata['kg_rel_text']:
				predicate = rel.split('-[')[1].split(']')[0]
				arg1 = rel.split(',')[0]
				arg2 = rel.split('-> ')[1]
				if self.get_relation_issues(arg1, predicate, arg2):
					continue
				if predicate == "instance_of":
					continue
				elif arg2 == 'true':
					init_block += f"\t\t({predicate} {arg1})\n"
					# if arg1 != "Robot":
					# 	objects.add(arg1)
				elif arg2 == 'None' or arg2 == 'false':
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
		task_pddl_file_name = os.path.join(self.log_dir, f"{self.time:04d}_problem.pddl")
		with open(task_pddl_file_name, "w") as f:
			f.write(task_pddl_)
		time.sleep(1)

		# C. run lapkt to plan
		plan_file_name = self.log_dir + f"/{self.time:04d}_plan.pddl"

		project_dir = Path(__file__).parent.parent.parent.as_posix()
		os.system(f"sudo docker run --rm -v {project_dir}:/root/experiments lapkt/lapkt-public ./siw-then-bfsf " + \
				  f"--domain /root/experiments/{self.domain_path} " + \
				  f"--problem /root/experiments/{task_pddl_file_name} " + \
				  f"--output /root/experiments/{plan_file_name} " + \
				  f"> {log_file}.pddl.log")
		
		with open(plan_file_name, "r") as f:
			plan = f.read().splitlines()
			self.process_plan(plan, truth_graph_store)

		self.time += 1
		return plan
	
	@staticmethod
	def is_condition_met(condition: tuple, param_names: dict[str, str], graph_store: AgeGraphStore):
		if condition[0] == 'not':
			return not KGAgent.is_condition_met(condition[1], param_names, graph_store)
		predicate, params = condition[0], condition[1:]
		arg1, arg2 = param_names[params[0]], param_names[params[1]] if len(params) == 2 else "true"
		return graph_store.rel_exists(arg1, predicate, arg2)

	def process_forall_effect(self, forall_effect: tuple, param_names: dict[str, str], truth_graph_store: AgeGraphStore):
		if forall_effect[0] != 'forall':
			return False
		quantifier_types = forall_effect[1:-1]
		param_names = param_names.copy()
		
		update = forall_effect[-1]
		assert update[0] == 'when'
		
		conditions = update[1]
		if conditions[0] == 'and':
			conditions = conditions[1:]
		else:
			conditions = [conditions]
		
		effects = update[2]
		if effects[0] == 'and':
			effects = effects[1:]
		else:
			effects = [effects]

		for entity_selection in itertools.product(*[self.entities_by_type[type] for _, _, type in quantifier_types]):
			for (quantifier, _, _), selection in zip(quantifier_types, entity_selection):
				param_names[quantifier] = selection
			if any(not KGAgent.is_condition_met(condition, param_names, self.graph_store) for condition in conditions):
				continue
			for effect in effects:
				remove = False
				if effect[0] == 'not':
					remove = True
					effect = effect[1]
				self.process_effect(effect, param_names, truth_graph_store, remove)
		
		return True
	
	def process_effect(self, effect: tuple[str], param_names: dict[str, str], truth_graph_store: AgeGraphStore, remove: bool = False):
		predicate, required_params = effect[0], effect[1:]
		if len(required_params) == 2:
			arg1 = param_names[required_params[0]]
			arg2 = param_names[required_params[1]]
			if remove:
				self.graph_store.delete(arg1, predicate, arg2)
				truth_graph_store.delete(arg1, predicate, arg2)
			else:
				if not self.graph_store.rel_exists(arg1, predicate, arg2):
					self.graph_store.upsert_triplet(arg1, predicate, arg2)
				if not truth_graph_store.rel_exists(arg1, predicate, arg2):
					truth_graph_store.upsert_triplet(arg1, predicate, arg2)
		elif len(required_params) == 1:
			arg = param_names[required_params[0]]
			if remove:
				if predicate != "held_by_robot":
					if not self.graph_store.rel_exists(arg, predicate, "false"):
						self.graph_store.upsert_triplet_bool(self.graph_store.name_to_id[arg], predicate, False)
					if not truth_graph_store.rel_exists(arg, predicate, "false"):
						truth_graph_store.upsert_triplet_bool(truth_graph_store.name_to_id[arg], predicate, False)
				self.graph_store.delete(arg, predicate, "true")
				truth_graph_store.delete(arg, predicate, "true")
			else:
				if not self.graph_store.rel_exists(arg, predicate, "true"):
					self.graph_store.upsert_triplet_bool(self.graph_store.name_to_id[arg], predicate, True)
				if not truth_graph_store.rel_exists(arg, predicate, "true"):
					truth_graph_store.upsert_triplet_bool(truth_graph_store.name_to_id[arg], predicate, True)
				if predicate != "held_by_robot":
					self.graph_store.delete(arg, predicate, "false")
					truth_graph_store.delete(arg, predicate, "false")
	
	def process_plan(self, plan: list[str], truth_graph_store: AgeGraphStore):
		for item in plan:
			tokens = item[1:-1].lower().split()
			action_name, args = tokens[0], tokens[1:]
			action = self.pddl_actions[action_name]

			assert len(args) == len(action.parameters)
			param_names = {}
			for token, name in zip(action.parameters, args):
				param_names[token[0]] = name
			
			# check if action is able to succeed in real environment
			if not (
				all(KGAgent.is_condition_met(pos_prec, param_names, truth_graph_store) for pos_prec in action.positive_preconditions) and
				all(KGAgent.is_condition_met(("not", neg_prec), param_names, truth_graph_store) for neg_prec in action.negative_preconditions)
			):
				print(f"Failure while processing plan at {item}")
				return
			
			for del_effect in action.del_effects:
				self.process_effect(del_effect, param_names, truth_graph_store, remove=True)

			for add_effect in action.add_effects:
				if not self.process_forall_effect(add_effect, param_names, truth_graph_store):
					self.process_effect(add_effect, param_names, truth_graph_store)

	def get_all_relations(self) -> list[str]:
		relations = self.graph_store.query("MATCH (V)-[R]->(V2) RETURN V.name, type(R), V2.name", return_count=3)
		return [" -> ".join(item[1:-1] for item in row) for row in relations if all(isinstance(s, str) for s in row)]
	
	def close(self) -> None:
		self.graph_store._conn.close()

