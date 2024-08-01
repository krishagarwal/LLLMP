import dataset
import importlib

for i in range(1, 6):
    print("Generating", i)
    while True:
        try:
            dataset = importlib.reload(dataset)
            generator = dataset.DatasetGenerator(f"experiments/experiment3/domains/domain{i}", num_state_changes=100, state_changes_per_query=300, state_changes_per_goal=5)
            generator.run()
            break
        except Exception as e:
            pass