import os
import sys

from dcr_sdk import Account, Simulation

P3_NAIVE = 2016062
ACTIVE_SIM = 2108620


def __main__():
    account = Account(os.environ["DCR_USERNAME"], os.environ["DCR_PASSWORD"])
    simulation = Simulation(P3_NAIVE, account, ACTIVE_SIM)
    if len(sys.argv) > 1 and sys.argv[1] == "zen":
        simulation.print_events(sys.argv[1] == "zen")
    else:
        simulation.print_events()
    # simulation.execute_event("A5")


__main__()

# ACCOUNT GRAPHS

# account = Account(os.environ["DCR_USERNAME"], os.environ["DCR_PASSWORD"])
#
# print('\n==== GRAPHS LISTING =====\n')
# for graph in account.get_graphs():
#     print(graph.id, graph.title)
#
# print('\n==== SIMULATION LISTING =====\n')
# for sim in account.get_sims(2016062):
#     print(sim.id, sim.title)

# simulation = Simulation(2016062,account)
# simulation.kill_simulation()
