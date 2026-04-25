IMAGE_NAME := pi-agent-isolated

.PHONY: build shell pi clean

build:
	podman build -t $(IMAGE_NAME) .

shell:
	./run.sh

pi:
	./run.sh pi

clean:
	podman rmi $(IMAGE_NAME) || true
