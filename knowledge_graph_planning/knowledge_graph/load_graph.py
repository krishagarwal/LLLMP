import logging
import sys

def load_graph(db_name: str, graph_name: str):
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)

    BUILD_INDEX = False

    from knowledge_graph.age import AgeGraphStore
    graph_store = AgeGraphStore(
        dbname=db_name,
        user="postgres",
        password="password",
        host="localhost",
        port=5432,
        graph_name=graph_name,
        node_label="entity"
    )
    conn = graph_store.client()

    # Create a new database session and return a new instance of the connection class
    cur = conn.cursor()

    cur.execute(f"LOAD 'age'")
    cur.execute(f"SET search_path = ag_catalog, '$user', public;")
    cur.execute(f"SELECT * FROM ag_catalog.drop_graph('{graph_name}', true)")
    cur.execute(f"SELECT * FROM ag_catalog.create_graph('{graph_name}')")
    cur.execute(f"SELECT * FROM ag_catalog.create_vlabel('{graph_name}', 'entity');")

    entities_query = "SELECT DISTINCT ON (instance_of.entity_id) \
                    instance_of.entity_id AS id, ea_str.attribute_value AS name, 'instance' as type \
                    FROM instance_of INNER JOIN entity_attributes_str AS ea_str \
                    ON instance_of.entity_id = ea_str.entity_id AND ea_str.attribute_name = 'name' \
                    AND instance_of.concept_name != 'pose' and instance_of.concept_name != 'region' and instance_of.concept_name != 'map' \
                    UNION SELECT concepts.entity_id AS id, concepts.concept_name AS name, 'concept' as type FROM concepts \
                    ORDER BY id ASC"

    cur.execute(entities_query)
    for row in cur.fetchall():
        id = row[0]
        name = row[1]
        type = row[2]
        cur.execute(f"SELECT * FROM cypher('{graph_name}', $$CREATE (a:entity {{id: '{id}', name: '{name}', type: '{type}'}}) RETURN a $$) as (a agtype);")

    def add_predicate_to_graph(predicate, query, cur):
        cur.execute(query)
        for row in cur.fetchall():
            cur.execute(f"SELECT * FROM cypher('{graph_name}', $$MATCH (u:entity {{id: '{row[0]}'}}), (v:entity {{id: '{row[2]}'}}) CREATE (u)-[e:{predicate}]->(v) RETURN e$$) as (e agtype);")

    attributes_query = "SELECT * FROM attributes WHERE attributes.type = 'id'"
    cur.execute(attributes_query)
    for row in cur.fetchall():
        predicate = row[0]
        attribute_query = f"SELECT ea_id.entity_id AS start_id, 'entity' as start_vertex_type, \
                            ea_id.attribute_value AS end_id, 'entity' as end_vertex_type \
                            FROM entity_attributes_id as ea_id \
                            WHERE ea_id.attribute_name = '{predicate}'"
        add_predicate_to_graph(predicate, attribute_query, cur)

    def add_value_and_predicate_to_graph(predicate, query, cur):
        cur.execute(query)
        for row in cur.fetchall():
            cur.execute(f"SELECT * FROM cypher('{graph_name}', $$MERGE (a:{row[3]} {{name: '{row[2]}'}}) RETURN a $$) as (a agtype);")
            cur.execute(f"SELECT * FROM cypher('{graph_name}', $$MATCH (u:entity {{id: '{row[0]}'}}), (v:{row[3]} {{name: '{row[2]}'}}) CREATE (u)-[e:{predicate}]->(v) RETURN e$$) as (e agtype);")
    
    value_types = ["float", "int", "bool"]

    for value_type in value_types:
        attributes_query = f"SELECT * FROM attributes WHERE attributes.type = '{value_type}'"
        cur.execute(attributes_query)
        for row in cur.fetchall():
            predicate = row[0]
            attribute_query = f"SELECT ea.entity_id AS start_id, 'entity' as start_vertex_type, \
                                ea.attribute_value AS end_value, '{value_type}' as end_vertex_type \
                                FROM entity_attributes_{value_type} as ea \
                                WHERE ea.attribute_name = '{predicate}'"
            add_value_and_predicate_to_graph(predicate, attribute_query, cur)

    instance_of_query = "SELECT instance_of.entity_id AS start_id, 'entity' AS start_vertex_type, \
                        concepts.entity_id AS end_id, 'entity' AS end_vertex_type \
                    FROM instance_of \
                    INNER JOIN concepts ON instance_of.concept_name = concepts.concept_name \
                    WHERE instance_of.concept_name != 'pose' and instance_of.concept_name != 'region' and instance_of.concept_name != 'map' \
                    ORDER BY start_id ASC "
    add_predicate_to_graph('instance_of', instance_of_query, cur)

    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    load_graph("knowledge_base", "knowledge_graph")