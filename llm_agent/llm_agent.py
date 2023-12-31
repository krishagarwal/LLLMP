import os
from llama_index import GPTVectorStoreIndex
from llama_index.data_structs.node import NodeWithScore
from llama_index.indices.query.schema import QueryBundle
from llama_index.indices.response.type import ResponseMode
from llama_index.data_structs import Node
from llama_index.indices.postprocessor import FixedRecencyPostprocessor
from llama_index.indices.postprocessor.types import BaseNodePostprocessor
from dataset.simulation import Agent, Simulation
from dataset.dataset import Dataset

# set API key
openai_keys_file = os.path.join(os.getcwd(), "keys/openai_keys.txt")
with open(openai_keys_file, "r") as f:
    keys = f.read()
keys = keys.strip().split('\n')
os.environ["OPENAI_API_KEY"] = keys[0]

class OrderPostProcessor(BaseNodePostprocessor):
	def __init__(self, initial_state: str) -> None:
		self.initial = NodeWithScore(Node("Initial state: " + initial_state))

	def postprocess_nodes(self, nodes: list[NodeWithScore], query_bundle: QueryBundle | None = None) -> list[NodeWithScore]:
		nodes.reverse()
		result_nodes = [self.initial]
		for i, node_with_score in enumerate(nodes):
			text = node_with_score.node.get_text()
			result_text = f"Step {i}: " + text[text.rindex("\n") + 1:]
			result_node = NodeWithScore(Node(result_text), node_with_score.score)
			result_nodes.append(result_node)
		return result_nodes

class LLMAgent(Agent):
	def input_initial_state(self, initial_state: str) -> None:
		self.state_change_count = 0
		self.index = GPTVectorStoreIndex([])
		post_processor = FixedRecencyPostprocessor(service_context=self.index.service_context)
		post_processor.top_k = 100
		self.query_engine = self.index.as_query_engine(
			response_mode=ResponseMode.SIMPLE_SUMMARIZE,
			similarity_top_k=100,
			node_postprocessors=[post_processor, OrderPostProcessor(initial_state)]
		)
	
	def input_state_change(self, state_change: str) -> None:
		self.state_change_count += 1
		self.index.insert_nodes([Node(state_change, extra_info={"date": self.state_change_count})])
	
	def answer_query(self, query: str) -> str:
		return str(self.query_engine.query(query)).strip()

if __name__ == "__main__":
	sim = Simulation(Dataset("simulation"), LLMAgent())
	sim.run()