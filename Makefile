.PHONY: test deploy

test:
	uv run pytest

deploy:
	ansible-playbook -i deploy/inventory.ini deploy/playbook.yml
