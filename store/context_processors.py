from .models import Category

def category_menu(request):
    root_categories = Category.objects.filter(parent__isnull=True)
    return {"root_categories": root_categories}