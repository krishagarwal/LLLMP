import os
from llama_index.core.indices.keyword_table.utils import extract_keywords_given_response
from llama_index.core.prompts import PromptTemplate, PromptType
from llama_index.core import ServiceContext

# read prompt template from file and format
def get_prompt_template(filename: str, **kwargs) -> str:
    with open(os.path.join(os.path.dirname(__file__), filename), "r") as f:
        contents = f.read()
    if not kwargs:
        return contents
    return contents.format(**kwargs)

def extract_keywords(service_context: ServiceContext,
                     template: str,
                     query_str: str,
                     max_keywords: int = 10,
                     result_start_token: str = "KEYWORDS:") -> list:
    # entities = graph_store.query("MATCH (V:entity) RETURN V.name")
    # entity_names = ", ".join([e[0].strip('\"') for e in entities])

    # ENTITY_SELECT_TEMPLATE = template.format(entity_names=entity_names)
    ENTITY_SELECT_PROMPT = PromptTemplate(
        template,
        prompt_type=PromptType.QUERY_KEYWORD_EXTRACT,
    )
    response = service_context.llm_predictor.predict(
        ENTITY_SELECT_PROMPT,
        max_keywords=max_keywords,
        question=query_str,
    )
    extracted_entities = extract_keywords_given_response(
        response, start_token=result_start_token, lowercase=False
    )
    return extracted_entities # type: ignore