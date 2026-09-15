from django.apps import AppConfig


class CatalogConfig(AppConfig):
    name = 'catalog'
    verbose_name = 'کاتالوگ محصولات'

    def ready(self):
        from . import signals  # noqa: F401
