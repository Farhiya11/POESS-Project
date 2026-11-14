
import sys

from dcr_engine import DCR_Engine, GraphDoesNotExistError


def __main__():
    args = sys.argv[1:]
    zen = "zen" in args
    titles = [arg for arg in args if arg != "zen"]

    engine = DCR_Engine(zen_mode=zen)

    print("\n==== SIMULATIONS =====\n")
    for graph_title, simulations in engine.simulations.items():
        for title, sim_id in simulations.items():
            print(engine.graphs[graph_title], sim_id, graph_title, "/", title)

    if len(titles) < 2:
        return

    graph_title, simulation_title = titles[0], titles[1]
    try:
        engine.attach_new_simulation(graph_title, simulation_title)
    except GraphDoesNotExistError as error:
        print(f"\n{error}")
        return

    # Same default name again, so the engine attaches a uuid to it
    engine.attach_new_simulation(graph_title, simulation_title)

    print("\n==== RUNNING SIMULATIONS =====\n")
    for reference_name in engine.running_simulations:
        print(reference_name)
    print()

    engine.running_simulations[simulation_title].print_events(engine.zen_mode)


if __name__ == "__main__":
    __main__()
