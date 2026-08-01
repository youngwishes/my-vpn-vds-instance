# Деплой VPN-ноды

Приложение доставляется на сервер напрямую из публичного GitHub-репозитория.
Один playbook устанавливает системные зависимости, обновляет ветку `main`,
создаёт постоянные ключи новой ноды, получает TLS-сертификат и запускает
Compose stack.

## Однократная локальная настройка

Скопируйте пример inventory в исключённый из Git файл:

```bash
cp deploy/inventory.example.ini deploy/inventory.ini
```

Укажите в нём `ansible_host`, SSH-пользователя и ключ. Публичные настройки при
необходимости задаются в секции `[vpn:vars]`:

```ini
[vpn]
vpn-node ansible_host=192.0.2.10 ansible_user=root ansible_ssh_private_key_file=~/.ssh/id_ed25519_deploy

[vpn:vars]
vpn_certbot_email=admin@example.com
```

Создайте локальный файл с общим `VPN_AGENT_TOKEN`, который уже настроен в
центральном backend. Это единственный секрет, передаваемый с Ansible controller:

```bash
mkdir -p deploy/secrets
chmod 700 deploy/secrets
printf '%s' '<VPN_AGENT_TOKEN>' > deploy/secrets/vpn-agent-token
chmod 600 deploy/secrets/vpn-agent-token
```

`deploy/inventory.ini` и весь `deploy/secrets/` исключены из Git. REALITY key
pair, short ID и Hysteria obfs заранее создавать не требуется.

По умолчанию используются:

- backend `https://beatvault.ru`;
- REALITY target/SNI `mtprotokeys.ru`;
- management listener `0.0.0.0:8443`;
- hostname Hysteria `<IPv4-с-дефисами>.sslip.io`.

Публичные overrides из
[`deploy/group_vars/vpn.example.yml`](../deploy/group_vars/vpn.example.yml)
можно поместить в `[vpn:vars]` inventory.

## Деплой

Из корня репозитория выполняется одна команда:

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml
```

Playbook:

1. проверяет публичный IPv4 и разрешение соответствующего `sslip.io` hostname;
2. устанавливает Docker Compose, Git, OpenSSL и Certbot;
3. клонирует или обновляет `main` из GitHub в `/opt/vpn-node`;
4. один раз создаёт уникальные node-specific REALITY и Hysteria параметры;
5. получает отдельный Let's Encrypt сертификат через HTTP-01 на TCP/80;
6. рендерит runtime-файлы с закрытыми правами;
7. запускает Compose и ожидает успешный `/health`;
8. выводит только публичные значения для создания `VPNInstance`.

Повторный запуск обновляет приложение, но сохраняет node-specific ключи в
`/opt/vpn-node/secrets/node-secrets.json`.

## Сертификат и renewal

Сертификат выпускается не на wildcard `*.sslip.io`, а на hostname конкретного
сервера, например `144-31-159-127.sslip.io`. Для выпуска и обновления сервер
должен принимать входящие TCP-соединения на порту 80.

Штатный `certbot.timer` периодически запускает renewal. После фактического
обновления deploy-hook копирует новый fullchain/private key в runtime-каталог и
пересоздаёт только контейнер `hysteria`; agent, Xray и management proxy не
затрагиваются.

Проверка renewal:

```bash
systemctl is-enabled certbot.timer
systemctl is-active certbot.timer
certbot renew --dry-run
RENEWED_LINEAGE=/etc/letsencrypt/live/<dash-separated-ip>.sslip.io \
  /etc/letsencrypt/renewal-hooks/deploy/vpn-node-hysteria
```

## Подключение ноды к backend

После deploy создайте в Django Admin одну неактивную `VPNInstance`, используя
публичный словарь из последней Ansible-задачи. Затем:

1. выполните admin action backfill для этой ноды;
2. дождитесь задач и при необходимости повторите backfill;
3. проверьте VLESS и Hysteria через клиент;
4. вручную активируйте ноду.

Пользовательские UUID и Hysteria credentials клонировать не нужно: backend
остаётся source of truth и передаёт их через bootstrap/backfill.
