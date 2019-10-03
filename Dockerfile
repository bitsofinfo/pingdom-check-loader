FROM python:3.7.4-alpine

ARG GIT_TAG=master

RUN echo GIT_TAG=${GIT_TAG}

# install the loader under /usr/local/bin
RUN apk update ; \
    apk upgrade ; \
    apk add git ; \
    echo $PATH ; \
    git clone --branch ${GIT_TAG} https://github.com/bitsofinfo/pingdom-check-loader.git ; \
    cd /pingdom-check-loader; git status; rm -rf .git; cd / ; \
    cp /pingdom-check-loader/*.py /usr/local/bin/ ; \
    rm -rf /pingdom-check-loader ; \
    apk del git ; \
    ls -al /usr/local/bin ; \
    chmod +x /usr/local/bin/*.py ; \
    rm -rf /var/cache/apk/*

# required modules
RUN pip install --upgrade pip pyyaml python-dateutil requests

ENV PATH="/usr/local/bin/;$PATH"
