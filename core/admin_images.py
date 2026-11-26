"""Admin tools for the WebP conversion: a superuser-only page (stats, confirmation, background run) and a
"convert selected images" action added to every admin whose model has image fields.

The page's URL is added in SportyAdminSite.get_urls; `install_action()` runs from SportyAdminConfig.ready,
after autodiscover has registered every ModelAdmin.
"""
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.template.response import TemplateResponse

from . import image_jobs
from .image_service import Summary, convert_stored_images, image_fields, stats
from .text import to_persian_digits


def size_label(n):
    return to_persian_digits(f'{n / 1024 / 1024:.1f}') + ' مگابایت'


def result_message(summary):
    fa = to_persian_digits
    return (
        f'{fa(summary.converted)} تصویر به WebP تبدیل شد، {fa(summary.skipped)} بدون تغییر، '
        f'{fa(summary.failed)} ناموفق؛ {size_label(summary.bytes_saved)} صرفه‌جویی.'
    )


def current_stats():
    found = stats()
    return {**found, 'size_label': size_label(found['bytes'])}


def convert_images_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    if request.method == 'POST':
        if request.POST.get('step') == 'run':
            keep = bool(request.POST.get('keep_originals'))
            if image_jobs.start(keep_originals=keep):
                messages.info(request, 'تبدیل تصاویر در پس‌زمینه شروع شد.')
            else:
                messages.warning(request, 'یک تبدیل در حال اجراست.')
            return redirect('admin:convert_images')
        context = {**admin.site.each_context(request), 'title': 'تأیید تبدیل تصاویر', 'stats': current_stats()}
        return TemplateResponse(request, 'admin/core/convert_images_confirm.html', context)

    job = image_jobs.status()
    if job and job['state'] in ('done', 'failed') and not job.get('reported'):
        if job['state'] == 'done':
            level = messages.WARNING if job['failed'] else messages.SUCCESS
            finished = Summary(converted=job['converted'], skipped=job['skipped'], failed=job['failed'],
                               bytes_before=job['saved'])
            messages.add_message(request, level, result_message(finished))
        else:
            messages.error(request, f'تبدیل تصاویر ناموفق بود: {job.get("error", "")}')
        image_jobs.mark_reported(job)
    running = bool(job and job['state'] == 'running')
    context = {
        **admin.site.each_context(request),
        'title': 'تبدیل تصاویر به WebP',
        'stats': None if running else current_stats(),
        'job': job,
        'running': running,
    }
    return TemplateResponse(request, 'admin/core/convert_images.html', context)


@admin.action(description='تبدیل تصاویر انتخاب‌شده به WebP', permissions=['change'])
def convert_selected_images(modeladmin, request, queryset):
    """Converts the selected rows' images, and the images of their inline rows (e.g. a product's gallery)."""
    summary = Summary()
    for queryset_to_convert in [queryset, *_inline_querysets(modeladmin, queryset)]:
        summary.add(convert_stored_images(queryset=queryset_to_convert))
    level = messages.WARNING if summary.failed else messages.SUCCESS
    modeladmin.message_user(request, result_message(summary), level)


def _inline_querysets(modeladmin, queryset):
    for inline_class in modeladmin.inlines:
        model = inline_class.model
        if not list(image_fields(model)):
            continue
        fk = next(
            (f for f in model._meta.get_fields()
             if f.is_relation and f.many_to_one and f.related_model is queryset.model),
            None,
        )
        if fk:
            yield model._default_manager.filter(**{f'{fk.name}__in': queryset})


def install_action(site):
    for model, model_admin in site._registry.items():
        has_images = list(image_fields(model)) or any(list(image_fields(i.model)) for i in model_admin.inlines)
        if has_images and convert_selected_images not in (model_admin.actions or []):
            model_admin.actions = [*(model_admin.actions or []), convert_selected_images]
