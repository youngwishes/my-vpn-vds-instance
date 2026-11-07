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

Добавляйте серверы в `[vpn]`, указывая только alias и `ansible_host`. Общие
SSH-параметры и публичные настройки задаются один раз в `[vpn:vars]`:

```ini
[vpn]
vpn-1 ansible_host=192.0.2.10
vpn-2 ansible_host=192.0.2.11

[vpn:vars]
ansible_user=root
ansible_ssh_private_key_file=~/.ssh/id_ed25519_deploy
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
- swap-файл `/swapfile` размером 2 ГиБ, только если активный swap отсутствует;
- REALITY target `mtprotokeys.com:443`, SNI `mtprotokeys.com`;
- management listener `0.0.0.0:8443`;
- hostname Hysteria `<IPv4-с-дефисами>.sslip.io`.

Публичные overrides из
[`deploy/group_vars/vpn.example.yml`](../deploy/group_vars/vpn.example.yml)
можно поместить в `[vpn:vars]` inventory.

## Узел только с Hysteria

Для отдельного узла добавьте `vpn_vless_enabled=false` в его строку inventory.
По умолчанию значение `true`: VLESS и Hysteria продолжают работать вместе.
Не задавайте `false` для всей группы, если остальные узлы должны сохранить VLESS.

Playbook устанавливает `docker-compose.hysteria-only.yml` как локальный
`docker-compose.override.yml`, удаляет существующий контейнер Xray и оставляет
Hysteria на UDP/443. Агент получает `VPN_VLESS_ENABLED=false` и обслуживает
bootstrap, профили и health без Xray. Поле `vless_uuid` в management API остаётся
для совместимости; сохранённые REALITY-ключи не удаляются. Генератор секретов
на новом узле пока создаёт полный набор транспортных ключей.

Обычные команды `docker compose` и обновление сертификата автоматически
учитывают override. Возврат `vpn_vless_enabled=true` и повторный деплой удаляют
override и восстанавливают оба протокола. В backend для этого же узла также
нужно отключить VLESS, чтобы убрать его из пользовательских подписок.

## Деплой

Из корня репозитория выполняется одна команда:

```bash
make deploy
```

Playbook:

1. проверяет публичный IPv4 и разрешение соответствующего `sslip.io` hostname;
2. устанавливает системные зависимости и создаёт постоянный `/swapfile`, если
   на сервере нет активного swap;
3. устанавливает Docker Compose при необходимости;
4. клонирует или обновляет `main` из GitHub в `/opt/vpn-node`;
5. один раз создаёт уникальные node-specific параметры либо безопасно импортирует
   их из существующего legacy runtime;
6. получает отдельный Let's Encrypt сертификат через HTTP-01 на TCP/80;
7. рендерит runtime-файлы с закрытыми правами;
8. запускает Compose и ожидает успешный `/health`;
9. выводит только публичные значения для создания `VPNInstance`.

Размер нового swap-файла задаётся переменной `vpn_swap_size_mb` и по умолчанию
равен `2048`. Если на сервере уже активен любой swap, playbook не меняет его.
Если активного swap нет, существующий `/swapfile`, который не является
обычным swap-файлом, не перезаписывается: деплой останавливается с ошибкой для
ручной проверки.

Повторный запуск обновляет приложение, но сохраняет node-specific ключи в
`/opt/vpn-node/secrets/node-secrets.json`.

## Миграция legacy-ноды

Работающую ноду старого формата можно добавить в тот же inventory и развернуть
обычной командой. Если `node-secrets.json` ещё отсутствует, но присутствуют оба
старых runtime-файла `secrets/xray-config.json` и
`secrets/hysteria-config.yaml`, playbook:

1. импортирует текущие REALITY private key, short ID и Hysteria obfs;
2. вычисляет соответствующий REALITY public key pinned Xray binary;
3. атомарно создаёт `node-secrets.json` с mode `0600`;
4. продолжает обычный deploy без ротации transport-параметров.

Если найден только один legacy-файл или структура конфигурации невалидна,
деплой останавливается до изменения runtime. После первой миграции сравните
выведенные public key, short ID и obfs с существующей `VPNInstance` в backend и
выполните smoke-check обоих протоколов.

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
