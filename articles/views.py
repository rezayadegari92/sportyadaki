from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from .models import Article

PAGE_SIZE = 12


def article_list(request):
    articles = Article.objects.published().select_related('category')
    return render(request, 'articles/article_list.html', {
        'page': Paginator(articles, PAGE_SIZE).get_page(request.GET.get('page')),
    })


def article_detail(request, slug):
    article = get_object_or_404(Article.objects.published().select_related('category', 'author'), slug=slug)
    return render(request, 'articles/article_detail.html', {'article': article})
