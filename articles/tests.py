from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Article


class ArticleTests(TestCase):
    def test_read_time_ignores_markup_and_rounds_up(self):
        self.assertEqual(Article(body='<p>کوتاه</p>').read_time_minutes, 1)
        self.assertEqual(Article(body='<p>' + 'کلمه ' * 201 + '</p>').read_time_minutes, 2)

    def test_published_excludes_drafts_and_scheduled(self):
        now = timezone.now()
        live = Article.objects.create(title='a', slug='a', body='x', status='publish', published_at=now)
        Article.objects.create(title='b', slug='b', body='x', status='draft', published_at=now)
        Article.objects.create(
            title='c', slug='c', body='x', status='publish', published_at=now + timedelta(days=1),
        )
        self.assertQuerySetEqual(Article.objects.published(), [live])


class ArticlePageTests(TestCase):
    def test_list_and_detail_show_only_published(self):
        live = Article.objects.create(
            title='تعویض روغن', slug='تعویض-روغن', body='<p>متن</p>', status='publish',
            published_at=timezone.now(),
        )
        draft = Article.objects.create(title='پیش‌نویس', slug='draft', body='x')

        listing = self.client.get(reverse('articles:list'))
        self.assertContains(listing, 'تعویض روغن')
        self.assertNotContains(listing, 'پیش‌نویس')
        self.assertContains(self.client.get(live.get_absolute_url()), '<p>متن</p>', html=True)
        self.assertEqual(self.client.get(draft.get_absolute_url()).status_code, 404)
