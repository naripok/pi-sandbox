IMAGE_NAME := pi-agent-isolated

.PHONY: build shell pi clean volumes reset images

install:
	./install.sh

build:
	podman build -t $(IMAGE_NAME) .

shell:
	./run.sh bash

pi:
	./run.sh pi

clean:
	podman rmi $(IMAGE_NAME) || true

volumes:
	@podman volume ls --filter name=pi-agent-persist- --format '{{.Name}}'

reset:
	./run.sh --reset

images:
	@podman images --filter "reference=pi-agent-isolated-*" --format "{{.Repository}}:{{.Tag}}" 2>/dev/null || true
