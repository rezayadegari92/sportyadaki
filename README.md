# اسپرت یدکی (Sportyadaki)

A Django storefront for auto parts and sport/accessory car gear, built to replace the
store's original WordPress + WooCommerce site. Persian-language, RTL, mobile-first.

Live at **[sportyadaki.shop](https://sportyadaki.shop)**.

## Stack

- Django 6.1, Python 3.12
- PostgreSQL in production, SQLite for local development
- Gunicorn (WSGI) behind Nginx, TLS via Let's Encrypt
- No frontend framework — server-rendered templates, vanilla JS, hand-written CSS
  (see `static/css/site.css`, which documents the design tokens at the top of the file)

## Apps

| App | Responsibility |
|---|---|
| `catalog` | Products, categories, car brands/models, part brands, ratings, related-product matching |
| `cart` | Session/user cart, stock checks, totals, shipping and checkout-suggestion logic |
| `orders` | Checkout, addresses, order tracking, staff order management |
| `payments` | Pluggable payment gateway interface + a console/placeholder implementation |
| `notifications` | Pluggable SMS interface + a console implementation |
| `accounts` | Customer accounts (phone + password login), staff login, dashboard |
| `articles` | Blog/articles section |
| `core` | Site-wide settings, homepage banners, checkout suggestions, the custom admin site |

Persian names in Django admin come from each app's `verbose_name` (see `apps.py`).

## Local setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo        # sample products, articles and banners; --clear to remove them
python manage.py runserver
```

By default `DEBUG=1` and the app uses `db.sqlite3` with no further configuration needed.

## Configuration

Settings are read from environment variables (see `config/settings.py`), and `.env` in the
project root is loaded automatically via `python-dotenv` if present.

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_DEBUG` | `1` | Set to `0` in production |
| `DJANGO_SECRET_KEY` | insecure dev key | **Required** when `DJANGO_DEBUG=0` |
| `DJANGO_ALLOWED_HOSTS` | *(empty)* | Comma-separated hostnames |
| `DB_ENGINE` | *(unset → SQLite)* | Set to `postgresql` to use Postgres |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | — | Required when `DB_ENGINE=postgresql` |
| `DB_HOST`, `DB_PORT` | `localhost`, `5432` | |
| `PAYMENT_GATEWAY` | `payments.gateways.placeholder.PlaceholderGateway` | Dev-only; raises if used with `DEBUG=0` |
| `SMS_SERVICE` | `notifications.sms.console.ConsoleSMSService` | Prints OTP/notification text to the console |

### Adding a real payment gateway or SMS provider

Both are behind small interfaces so a real integration doesn't touch checkout, order or
notification code:

- Payment gateways: implement `payments/gateways/base.py`'s `PaymentGatewayService`
  (see the docstring there for the request → callback → verify flow), then point
  `PAYMENT_GATEWAY` at it.
- SMS: implement `notifications/sms/base.py`'s interface, then point `SMS_SERVICE` at it.

## Tests

```bash
python manage.py test
```

## Deployment

Runs on a single VPS: Gunicorn (systemd service `gunicorn-sportyadaki`, unix socket) behind
Nginx, PostgreSQL, static files served directly by Nginx from `STATIC_ROOT`.

```bash
git pull origin main
venv/bin/pip install -r requirements.txt   # if requirements changed
venv/bin/python manage.py migrate          # if there are new migrations
venv/bin/python manage.py collectstatic --noinput
systemctl restart gunicorn-sportyadaki     # only needed for .py/template changes;
                                            # static-only changes just need collectstatic
```

Django caches compiled templates in memory when `DEBUG=0`, so any `.py` or template edit
needs the Gunicorn restart above to take effect — static assets (CSS/JS/images) don't.
