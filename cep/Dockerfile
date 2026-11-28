FROM siddhiio/siddhi-runner-alpine:5.1.0 AS script-extension-downloader
USER root
RUN wget -q \
    "https://repo.maven.apache.org/maven2/io/siddhi/extension/script/js/siddhi-script-js/5.0.4/siddhi-script-js-5.0.4.jar" \
    -O /tmp/siddhi-script-js-5.0.4.jar

FROM siddhiio/siddhi-runner-alpine:5.1.0

WORKDIR /apps
COPY apps/DCRApp.siddhi /apps/DCRApp.siddhi
COPY apps/PreparednessDecisionApp.siddhi /apps/PreparednessDecisionApp.siddhi

ARG SIDDHI_RUNNER_LIB=/home/siddhi/wso2-siddhi-runner-5.1.0/lib
COPY --from=script-extension-downloader \
    /tmp/siddhi-script-js-5.0.4.jar \
    ${SIDDHI_RUNNER_LIB}/siddhi-script-js-5.0.4.jar

CMD ["-Dapps=/apps"]
