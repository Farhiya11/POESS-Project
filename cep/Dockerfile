FROM siddhiio/siddhi-runner-alpine:5.1.0

WORKDIR /apps
COPY apps/OrderFoodAppDEMO.siddhi /apps/OrderFoodAppDEMO.siddhi
COPY apps/DCRApp.siddhi /apps/DCRApp.siddhi
COPY apps/FloodDecisionApp.siddhi /apps/FloodDecisionApp.siddhi

CMD ["-Dapps=/apps"]
