import os

from dcr_sdk import Account, Simulation

P3_NAIVE = 2016062

account = Account(os.environ["DCR_USERNAME"], os.environ["DCR_PASSWORD"])
simulation = Simulation(P3_NAIVE, account)

# ACCOUNT GRAPHS

print('\n==== GRAPHS LISTING =====\n')
for graph in account.get_graphs():
    print(graph.id, graph.title)

print('\n==== SIMULATION LISTING =====\n')
for sim in account.get_sims(2016062):
    print(sim.id, sim.title)
