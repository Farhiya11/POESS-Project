import sys

from dcr_engine import (
    DCR_Engine,
    GraphDoesNotExistError,
    RequestNonConformanceError,
)


def print_overview(engine: DCR_Engine) -> None:
    overview = engine.get_overview()
    print("\n==== GRAPHS =====\n")
    for graph_title, simulations in overview.simulations.items():
        print(graph_title, overview.graphs[graph_title])
        for sim_title, sim_id in simulations.items():
            print("   ", sim_title, sim_id)
    print("\n==== RUNNING =====\n")
    for name, status in overview.running.items():
        print(name, status)
    print()


# Usage: main.py [zen] <graph_title> <simulation_title> [event_id ...]
def __main__():
    args = sys.argv[1:]
    zen = "zen" in args
    titles = [arg for arg in args if arg != "zen"]

    engine = DCR_Engine(zen_mode=zen)

    print_overview(engine)

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

    # Any extra arguments are executed in order as one sequence
    sequence = titles[2:]
    if sequence:
        print(f"==== EXECUTING {' -> '.join(sequence)} =====\n")
        try:
            engine.execute_sequence(simulation_title, sequence)
        except RequestNonConformanceError as error:
            print(f"Request Non-Conformance: {error}\n")

    print_overview(engine)
    engine.running_simulations[simulation_title].print_events(engine.zen_mode)

    print("\n==== SHOW NEXT EVENTS =====\n")
    for event in engine.show_next_event(simulation_title):
        print(event.id, event.label)


if __name__ == "__main__":
    __main__()
