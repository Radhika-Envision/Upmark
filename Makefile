VERSION := $(shell git describe --tags | sed 's,^v\([0-9]\),\1,')
DOCKER_BIN := $(shell which docker || which docker.io)
ifeq (,$(findstring docker, $(shell groups)))
	DOCKER_BIN := sudo $(DOCKER_BIN)
endif
DOCKER_TAG := vpac/aquamark

.PHONY: all
all: build

.PHONY: build
build: src/app/version.txt
	$(DOCKER_BIN) build -t $(DOCKER_TAG) src/app
	$(DOCKER_BIN) tag $(DOCKER_TAG) $(DOCKER_TAG):latest
	$(DOCKER_BIN) tag $(DOCKER_TAG) $(DOCKER_TAG):$(VERSION)

.PHONY: version
version: src/app/version.txt

src/app/version.txt:
	echo $(VERSION) > src/app/version.txt
