.PHONY: deploy logs status restart ssh sync

deploy:
	@scripts/deploy.sh

logs:
	@scripts/logs.sh

status:
	@scripts/status.sh

restart:
	@scripts/restart.sh

ssh:
	@scripts/ssh.sh

sync:
	@uv sync
