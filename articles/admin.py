from django.contrib import admin

from core.admin_display import badge, thumbnail

from .models import Article, ArticleCategory


@admin.register(ArticleCategory)
class ArticleCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('thumb', 'title', 'category', 'status_badge', 'published_at')
    list_display_links = ('thumb', 'title')
    list_filter = ('status', 'category')
    search_fields = ('title', 'body')
    prepopulated_fields = {'slug': ('title',)}
    autocomplete_fields = ('category', 'author')
    date_hierarchy = 'published_at'

    @admin.display(description='تصویر')
    def thumb(self, obj):
        return thumbnail(obj.featured_image)

    @admin.display(description='وضعیت', ordering='status')
    def status_badge(self, obj):
        return badge(obj.get_status_display(), 'green' if obj.status == Article.Status.PUBLISHED else 'gray')
