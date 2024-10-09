import os
from llama_index.core.indices.keyword_table.utils import extract_keywords_given_response
from llama_index.core.prompts import PromptTemplate, PromptType
from llama_index.core import ServiceContext
from llama_index.core.llms.llm import LLM
import psycopg2
from psycopg2 import sql


def reset_database(dbname, user, password, host, port, schema_file):
    # Connect to PostgreSQL
    try:
        conn = psycopg2.connect(dbname='postgres', user=user, password=password, host=host, port=port)
        conn.autocommit = True  # Ensure we can execute CREATE/DROP DATABASE statements
        cur = conn.cursor()

        # Optionally drop and recreate the database (useful for full reset)
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {};").format(sql.Identifier(dbname)))
        cur.execute(sql.SQL("CREATE DATABASE {};").format(sql.Identifier(dbname)))
        conn.commit()

        # Now reconnect to the newly created database (if dropped and recreated)
        cur.close()
        conn.close()
        conn = psycopg2.connect(dbname=dbname, user=user, password=password, host=host, port=port)
        cur = conn.cursor()

        # Open and execute the schema file
        with open(schema_file, 'r') as f:
            schema_sql = f.read()

        # Execute the schema SQL
        cur.execute(schema_sql)
        conn.commit()
        print("Database has been reset and schema executed successfully.")

    except Exception as error:
        print(f"Error: {error}")

    finally:
        if conn:
            cur.close()
            conn.close()


# read prompt template from file and format
def get_prompt_template(filename: str, **kwargs) -> str:
    with open(os.path.join(os.path.dirname(__file__), filename), "r") as f:
        contents = f.read()
    if not kwargs:
        return contents
    return contents.format(**kwargs)


def extract_keywords(llm: LLM,
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
    response = llm.predict(
        ENTITY_SELECT_PROMPT,
        max_keywords=max_keywords,
        question=query_str,
    )
    extracted_entities = extract_keywords_given_response(
        response, start_token=result_start_token, lowercase=False
    )
    return extracted_entities  # type: ignore
