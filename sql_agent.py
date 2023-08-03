import openai
import json
import subprocess
import tempfile
from simulation import Agent, Simulation
from dataset import Dataset
from knowledge_representation import get_default_ltmc
from knowledge_representation.knowledge_loader import load_knowledge_from_yaml, populate_with_knowledge

openai.api_key = # API KEY

class SQLAgent(Agent):
	initial_prompt = \
"You have access to a PostgreSQL database that describes information about the state of a household. "  \
"You are an agent that will perform tasks around the household using the information in the database. " \
"""This is the database schema:

```

/* A table of entity ids. An entity is either an object in the household or a concept. Each entity has a unique entity_id */
CREATE TABLE entities
(
	entity_id SERIAL NOT NULL,
	PRIMARY KEY (entity_id)
);

CREATE TYPE attribute_type as ENUM ('id', 'bool', 'int', 'float', 'str');

/* Table of the attributes that entities can have, including the name of the attribute and its data type */
CREATE TABLE attributes
(
	attribute_name varchar(24)    NOT NULL,
	type           attribute_type NOT NULL,
	PRIMARY KEY (attribute_name)
);

/* Table of concepts in the household, including the name and antity_id. */
CREATE TABLE concepts
(
	entity_id int NOT NULL,
	concept_name varchar(24) NOT NULL UNIQUE,
	PRIMARY KEY (entity_id, concept_name),
		FOREIGN KEY (entity_id)
		REFERENCES entities (entity_id)
		ON DELETE CASCADE
		ON UPDATE CASCADE
);

/* A table with each entity's object type (its concept). */
CREATE TABLE instance_of
(
	entity_id int NOT NULL,
	concept_name varchar(24) NOT NULL,
	PRIMARY KEY (entity_id, concept_name),
	FOREIGN KEY (entity_id)
		REFERENCES entities (entity_id)
		ON DELETE CASCADE
		ON UPDATE CASCADE,
	FOREIGN KEY (concept_name)
		REFERENCES concepts (concept_name)
		ON DELETE CASCADE
		ON UPDATE CASCADE
);


/* A table of all the attributes objects have where the attribute is another entity (stored as the entity_id). It might be worthwhile to separately investigate attributes associated with the entity_ids found here */
CREATE TABLE entity_attributes_id
(
	entity_id       int         NOT NULL,
	attribute_name  varchar(24) NOT NULL,
	attribute_value int         NOT NULL,
	PRIMARY KEY (entity_id, attribute_name, attribute_value),
	FOREIGN KEY (entity_id)
		REFERENCES entities (entity_id)
		ON DELETE CASCADE
		ON UPDATE CASCADE,
	FOREIGN KEY (attribute_name)
		REFERENCES attributes (attribute_name)
		ON DELETE CASCADE
		ON UPDATE CASCADE,
	FOREIGN KEY (attribute_value)
		REFERENCES entities (entity_id)
		ON DELETE CASCADE
		ON UPDATE CASCADE
);

/* A table of all the attributes objects have where the attribute is of type integer */
CREATE TABLE entity_attributes_int
(
	entity_id       int         NOT NULL,
	attribute_name  varchar(24) NOT NULL,
	attribute_value int         NOT NULL,
	PRIMARY KEY (entity_id, attribute_name, attribute_value),
	FOREIGN KEY (entity_id)
		REFERENCES entities (entity_id)
		ON DELETE CASCADE
		ON UPDATE CASCADE,
	FOREIGN KEY (attribute_name)
		REFERENCES attributes (attribute_name)
		ON DELETE CASCADE
		ON UPDATE CASCADE
);

/* A table of all the attributes objects have where the attribute is of type string */
CREATE TABLE entity_attributes_str
(
	entity_id       int         NOT NULL,
	attribute_name  varchar(24) NOT NULL,
	attribute_value varchar(24) NOT NULL,
	PRIMARY KEY (entity_id, attribute_name, attribute_value),
	FOREIGN KEY (entity_id)
		REFERENCES entities (entity_id)
		ON DELETE CASCADE
		ON UPDATE CASCADE,
	FOREIGN KEY (attribute_name)
		REFERENCES attributes (attribute_name)
		ON DELETE CASCADE
		ON UPDATE CASCADE
);

/* A table of all the attributes objects have where the attribute is of type float */
CREATE TABLE entity_attributes_float
(
	entity_id       int         NOT NULL,
	attribute_name  varchar(24) NOT NULL,
	attribute_value double precision NOT NULL,
	PRIMARY KEY (entity_id, attribute_name, attribute_value),
	FOREIGN KEY (entity_id)
		REFERENCES entities (entity_id)
		ON DELETE CASCADE
		ON UPDATE CASCADE,
	FOREIGN KEY (attribute_name)
		REFERENCES attributes (attribute_name)
		ON DELETE CASCADE
		ON UPDATE CASCADE
);

/* A table of all the attributes objects have where the attribute is of type boolean */
CREATE TABLE entity_attributes_bool
(
	entity_id       int         NOT NULL,
	attribute_name  varchar(24) NOT NULL,
	attribute_value bool,
	PRIMARY KEY (entity_id, attribute_name, attribute_value),
	FOREIGN KEY (entity_id)
		REFERENCES entities (entity_id)
		ON DELETE CASCADE
		ON UPDATE CASCADE,
	FOREIGN KEY (attribute_name)
		REFERENCES attributes (attribute_name)
		ON DELETE CASCADE
		ON UPDATE CASCADE
);
```

""" \
"You will be asked a query by the user. " \
"You are allowed to run arbitrarily many SQL queries on the database to gather the information you need to answer the user query. " \
"First determine what the attributes and their types are to find out what information you can query for. " \
"Then determine which objects are relevant to the user query and keep track of their entity_id. " \
"Then collect information about those objects by querying the attribute tables with those entity_id's. " \
"Try to make your queries only match specific entity_ids. "

	functions = [
		{
			"name": "run_sql",
			"description": "Runs a given SQL query and returns the result",
			"parameters": {
				"type": "object",
				"properties": {
					"query": {
						"type": "string",
						"description": "A syntactically correct SQL query",
					},
					"reasoning": {
						"type": "string",
						"description": "A short explanation of how the SQL query will help answer the user query"
					}
				}
			}
		}
	]

	def __init__(self, verbose: bool = False) -> None:
		self.verbose = verbose

	def run_psql_command(self, command: str):
		try:
			# Run the psql command as a subprocess
			psql_process = subprocess.Popen(
				["psql", "postgresql://postgres:password@localhost:5432/knowledge_base", "-c", command, "-P", "pager=off", "-P", "footer=off"],
				stdin=subprocess.PIPE,
				stdout=subprocess.PIPE,
				stderr=subprocess.PIPE,
				text=True  # This ensures that the output is returned as text
			)

			# Wait for the process to complete and fetch the output
			stdout, stderr = psql_process.communicate()

			# Check if there were any errors
			if psql_process.returncode == 0:
				# Successful execution
				return stdout
			else:
				# Error occurred
				return f"Error executing SQL query:\n{stderr}"
		except Exception as e:
			return f"Error executing SQL query: {str(e)}"		

	def input_initial_state(self, initial_state: str, knowledge_yaml: str) -> None:
		with tempfile.NamedTemporaryFile(mode='w') as temp_yaml_file:
			temp_yaml_file.write(knowledge_yaml)
			all_knowledge = [load_knowledge_from_yaml(temp_yaml_file.name)]
		concept_count, instance_count = populate_with_knowledge(get_default_ltmc(), all_knowledge)
		if self.verbose:
			print("Loaded {} concepts and {} instances".format(concept_count, instance_count))
		self.attributes = self.run_psql_command("SELECT * FROM attributes")
		self.entity_names = self.run_psql_command("SELECT * from entity_attributes_str WHERE attribute_name = 'name'")
		if self.verbose:
			print(self.attributes)
			print(self.entity_names)
	
	def input_state_change(self, state_change: str) -> None:
		pass

	def answer_query(self, query: str) -> str:
		messages = [
			{
				"role": "system",
				"content": SQLAgent.initial_prompt
			},
			{
				"role": "user",
				"content": query
			},
			{
				"role": "assistant",
				"content": None,
				"function_call": {
					"name": "run_sql",
					"arguments": \
"""{
	"query": "SELECT * FROM attributes",
	"reasoning": "I want to know what different attributes objects can have"
}"""
				}
			},
			{
				"role": "function",
				"name": "run_sql",
				"content": self.attributes
			},
			{
				"role": "assistant",
				"content": None,
				"function_call": {
					"name": "run_sql",
					"arguments": \
"""{
	"query": "SELECT entity_id, attribute_name, attribute_value from entity_attributes_str WHERE attribute_name = 'name'",
	"reasoning": "I want to know the names of all the objects to find out which ones are relevant to the user query"
}"""
				}
			},
			{
				"role": "function",
				"name": "run_sql",
				"content": self.entity_names
			}
		]

		while True:
			response = openai.ChatCompletion.create(
				model="gpt-3.5-turbo-0613",
				messages=messages,
				functions=SQLAgent.functions,
				function_call="auto",
				temperature=0
			)
			message = response["choices"][0]["message"]
			messages.append(message)

			if message.get("function_call"):
				if message["function_call"]["name"] != "run_sql":
					raise ValueError("Invalid function call: " + str(message))
				args = json.loads(message["function_call"]["arguments"])
				if not args.get("query"):
					raise ValueError("Did not pass in 'query' parameter")
				sql_query = args["query"]
				if not isinstance(sql_query, str):
					raise ValueError("Invalid type for 'query' argument")
				response = self.run_psql_command(sql_query)
				if self.verbose:
					print("SQL query: ", sql_query)
					print(f"Response:\n", response)
				messages.append({
					"role": "function",
					"name": "run_sql",
					"content": response
				})
				if self.verbose:
					print(message)
			else:
				break

		return message["content"]

def main():
	sim = Simulation(Dataset("test"), SQLAgent(verbose=True))
	sim.run()

if __name__ == "__main__":
	main()