# Repository Guidelines

## Project Structure

- `ibands_site/` contains project URLs and shared infrastructure. Its `settings/` package splits shared, development, and production settings.
- `store/` owns the catalog, cart, checkout, orders, promotions, and shop admin. `customer/` owns account pages, saved addresses, and wishlists. `userauths/` owns authentication and the custom user model. Each app keeps its migrations in `migrations/`.
- Django templates live in `templates/`, grouped by app or purpose. Styles, scripts, images, and favicons live in `static/assets/`.

## Local Development

Use the Python version in `.python-version`. Create and activate a virtual environment with `python -m venv ~/.venvs/ibands` and `source ~/.venvs/ibands/bin/activate`. Set `ENVIRONMENT=dev` and supply `DEVELOPMENT_DATABASE_URL` and the variables required by `ibands_site/settings/base.py`. Keep local credentials in the ignored `.env` file.

- `python -m pip install -r requirements.txt` installs dependencies.
- `python manage.py migrate` applies migrations to the development database.
- `python manage.py runserver` starts the local site.
- `python manage.py check` checks Django configuration.
- `python manage.py collectstatic --noinput` assembles static assets locally into `staticfiles/` under development settings.

## Style and Naming

Use four spaces for Python and match the surrounding Django template indentation. Use `snake_case` for Python functions and modules, `PascalCase` for classes, and an underscore prefix for template partials such as `_product_card.html`. Prettier uses four spaces and excludes HTML templates.

## Testing

Run `python manage.py test` for the full Django suite or `python manage.py test store.test_tracking` for one module. Use Django’s `TestCase` or `SimpleTestCase` in app-level `tests.py` or `test_*.py` files, with descriptive `test_*` methods. Use an isolated development database configuration that allows Django to create a test database, and mock external services such as Stripe and couriers. The repository has no configured coverage threshold.

## Commits and Pull Requests

Follow recent scoped subjects such as `fix(shop): keep the photo on screen` or `feat(checkout): add a delivery option`. Describe the behavior change and verification in the PR, link related issues, and include screenshots for visible changes. For production pushes, follow the existing [static publishing](.cursor/rules/collectstatic.mdc) and [staff update](.cursor/rules/whats-new.mdc) rules.
